import { afterEach, describe, expect, it } from 'vitest';

import { TECH_INDEX_HTML, bootPage, flush, scriptsFor, stubFetch } from './helpers.js';

const TECH = [
    { name: 'Python', count: 191 },
    { name: 'TypeScript', count: 48 },
    { name: 'Zig', count: 1 },
    { name: 'Triton', count: 1 },
];

async function boot(body = TECH) {
    const calls = stubFetch({ '/api/tech': { body } });
    bootPage({ html: TECH_INDEX_HTML, script: 'tech-index.js',
               extraScripts: scriptsFor('tech-index.html', 'tech-index.js') });
    await flush();
    return calls;
}

afterEach(() => { delete globalThis.fetch; });

describe('listing every technology', () => {
    it('says how many there are', async () => {
        await boot();
        expect(document.getElementById('techIndexCount').textContent).toContain('4');
    });

    it('links each one to its page', async () => {
        await boot();
        const links = [...document.querySelectorAll('#techIndex a')];

        expect(links.length).toBe(4);
        expect(links[0].getAttribute('href')).toBe('/tech/Python');
    });

    it('shows the count beside the name', async () => {
        await boot();
        expect(document.querySelector('#techIndex a').textContent).toBe('Python (191)');
    });

    it('escapes a name that needs it', async () => {
        await boot([{ name: 'ROS 2', count: 3 }]);
        expect(document.querySelector('#techIndex a').getAttribute('href'))
            .toBe('/tech/ROS%202');
    });

    it('clears the busy flag', async () => {
        await boot();
        expect(document.getElementById('techIndex').getAttribute('aria-busy')).toBe('false');
    });
});

describe('separating the shared from the long tail', () => {
    it('groups them, because they answer different questions', async () => {
        /** Two thirds of the technologies are used by a single agent.
         *  Sorted together, the ones worth browsing are buried. */
        await boot();
        const headings = [...document.querySelectorAll('.tech-group h2')].map(h => h.textContent);

        expect(headings).toEqual(['Used by several agents (2)', 'Used by one agent (2)']);
    });

    it('omits a group with nothing in it', async () => {
        await boot([{ name: 'Python', count: 191 }]);
        const headings = [...document.querySelectorAll('.tech-group h2')].map(h => h.textContent);

        expect(headings).toEqual(['Used by several agents (1)']);
    });
});

describe('filtering', () => {
    async function type(text) {
        const filter = document.getElementById('techFilter');
        filter.value = text;
        filter.dispatchEvent(new window.Event('input'));
        await flush();
    }

    it('narrows to what matches', async () => {
        await boot();
        await type('typ');

        const names = [...document.querySelectorAll('#techIndex a')].map(a => a.textContent);
        expect(names).toEqual(['TypeScript (48)']);
    });

    it('ignores case', async () => {
        await boot();
        await type('PYTHON');
        expect(document.querySelectorAll('#techIndex a')).toHaveLength(1);
    });

    it('says so when nothing matches', async () => {
        await boot();
        await type('cobol');
        expect(document.getElementById('techIndex').textContent).toContain('cobol');
    });

    it('restores everything when cleared', async () => {
        await boot();
        await type('typ');
        await type('');
        expect(document.querySelectorAll('#techIndex a')).toHaveLength(4);
    });
});

describe('when the API fails', () => {
    it('says so rather than staying on Loading', async () => {
        stubFetch({ '/api/tech': { ok: false, status: 500, body: {} } });
        bootPage({ html: TECH_INDEX_HTML, script: 'tech-index.js',
                   extraScripts: scriptsFor('tech-index.html', 'tech-index.js') });
        await flush();

        expect(document.getElementById('techIndex').textContent).toContain('Could not load');
        expect(document.getElementById('techIndexCount').textContent).not.toBe('Loading…');
    });
});

describe('the busy flag', () => {
    it('is cleared when nothing matches the filter', async () => {
        /** The early return skipped the line that clears it, leaving a live
         *  region marked busy for good. */
        await boot();
        const filter = document.getElementById('techFilter');
        filter.value = 'cobol';
        filter.dispatchEvent(new window.Event('input'));
        await flush();

        expect(document.getElementById('techIndex').getAttribute('aria-busy')).toBe('false');
    });

    it('is cleared when there are no technologies at all', async () => {
        await boot([]);
        expect(document.getElementById('techIndex').getAttribute('aria-busy')).toBe('false');
    });
});
