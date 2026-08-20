import { afterEach, describe, expect, it } from 'vitest';

import { CHANGES_HTML, bootPage, flush, scriptsFor, stubFetch } from './helpers.js';

const QUALITY = {
    latest: {
        at: '2026-08-20T09:00:00+00:00', commit: 'abc1234', agents: 321, limit: 10,
        categories: { Infrastructure: 0.924, Safety: 0.976, 'Data Analysis': 1.0 },
        guards: 127, failing: 0, thinnest: 0.0325,
    },
    moved: [{ category: 'Automation', from: 0.895, to: 0.946, delta: 0.051 }],
    runs: [], metadata: { count: 5 },
};

function boot(routes) {
    const calls = stubFetch({ '/api/changelog': { body: { entries: [] } }, ...routes });
    bootPage({ html: CHANGES_HTML, script: 'quality-panel.js',
               extraScripts: scriptsFor('changes.html', 'quality-panel.js') });
    return calls;
}

afterEach(() => { delete globalThis.fetch; });

describe('showing how findable the catalogue is', () => {
    it('lists every category, weakest first', async () => {
        boot({ '/api/quality': { body: QUALITY } });
        await flush();

        const names = [...document.querySelectorAll('.quality-name')].map(n => n.textContent);
        expect(names).toEqual(['Infrastructure', 'Safety', 'Data Analysis']);
    });

    it('names the weakest category in the summary', async () => {
        boot({ '/api/quality': { body: QUALITY } });
        await flush();

        const summary = document.querySelector('.quality-summary').textContent;
        expect(summary).toContain('Infrastructure');
        expect(summary).toContain('0.924');
        expect(summary).toContain('321 agents');
    });

    it('draws the bar to the score', async () => {
        boot({ '/api/quality': { body: QUALITY } });
        await flush();

        const widths = [...document.querySelectorAll('.quality-fill')].map(f => f.style.width);
        expect(widths).toEqual(['92.4%', '97.6%', '100%']);
    });

    it('reports what moved, and which way', async () => {
        boot({ '/api/quality': { body: QUALITY } });
        await flush();

        const moved = document.querySelector('.quality-moved li');
        expect(moved.textContent).toContain('Automation +0.051');
        expect(moved.className).toBe('quality-rose');
    });

    it('marks a fall differently from a rise', async () => {
        boot({ '/api/quality': { body: { ...QUALITY,
            moved: [{ category: 'Safety', from: 0.976, to: 0.849, delta: -0.127 }] } } });
        await flush();

        const moved = document.querySelector('.quality-moved li');
        expect(moved.className).toBe('quality-fell');
        expect(moved.textContent).toContain('-0.127');
    });

    it('says nothing about movement when nothing moved', async () => {
        boot({ '/api/quality': { body: { ...QUALITY, moved: [] } } });
        await flush();

        expect(document.querySelector('.quality-moved')).toBeNull();
        expect(document.getElementById('qualityArea').textContent)
            .not.toContain('Since the previous');
    });

    it('clears the busy flag once it has rendered', async () => {
        boot({ '/api/quality': { body: QUALITY } });
        await flush();

        expect(document.getElementById('qualityArea').getAttribute('aria-busy')).toBe('false');
    });
});

describe('when there is nothing to show', () => {
    it('stays quiet when no run has been recorded', async () => {
        /** Not an error: nobody has measured yet, and the history below is
         *  still the reason to be on this page. */
        boot({ '/api/quality': { body: { latest: null, runs: [], moved: [] } } });
        await flush();

        const area = document.getElementById('qualityArea');
        expect(area.textContent.trim()).toBe('');
        expect(area.getAttribute('aria-busy')).toBe('false');
    });

    it('reports a failure without taking the page with it', async () => {
        /** The two panels load independently on purpose. The change history
         *  is why people come here; it must not vanish because the quality
         *  file is missing or the endpoint is down. */
        boot({ '/api/quality': { ok: false, status: 500 } });
        await flush();

        expect(document.getElementById('qualityArea').textContent)
            .toMatch(/Could not load the quality scores/);
        expect(document.getElementById('changesArea')).not.toBeNull();
    });

    it('ignores a category whose score is not a number', async () => {
        boot({ '/api/quality': { body: { ...QUALITY,
            latest: { ...QUALITY.latest, categories: { Safety: 0.9, Broken: null } } } } });
        await flush();

        const names = [...document.querySelectorAll('.quality-name')].map(n => n.textContent);
        expect(names).toEqual(['Safety']);
    });
});
