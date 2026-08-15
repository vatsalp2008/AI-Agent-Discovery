import { afterEach, describe, expect, it } from 'vitest';

import { CHANGES_HTML, bootPage, flush, scriptsFor, stubFetch } from './helpers.js';

function entry(overrides = {}) {
    return {
        commit: 'abc12345',
        at: '2026-08-14T10:00:00+00:00',
        subject: 'Add 20 agents to the thinnest categories',
        total: 223,
        added: [],
        removed: [],
        edited: [],
        ...overrides,
    };
}

async function boot(entries = [entry()]) {
    const calls = stubFetch({
        '/api/changelog': { body: { entries, metadata: { count: entries.length } } },
    });
    bootPage({ html: CHANGES_HTML, script: 'changes.js',
               extraScripts: scriptsFor('changes.html', 'changes.js') });
    await flush();
    return calls;
}

afterEach(() => { delete globalThis.fetch; });

describe('listing the history', () => {
    it('renders an entry per commit', async () => {
        await boot([entry(), entry({ subject: 'Follow two renames' })]);
        expect(document.querySelectorAll('.change-entry')).toHaveLength(2);
    });

    it('shows the commit subject as the heading', async () => {
        await boot();
        expect(document.querySelector('.change-entry h2').textContent)
            .toBe('Add 20 agents to the thinnest categories');
    });

    it('says how big the catalogue was at that point', async () => {
        await boot();
        expect(document.querySelector('.change-meta').textContent).toContain('223 agents');
    });

    it('clears the busy flag once loaded', async () => {
        await boot();
        expect(document.getElementById('changesArea').getAttribute('aria-busy')).toBe('false');
    });
});

describe('what an entry says', () => {
    it('links each added agent to its page', async () => {
        await boot([entry({ added: ['Kedro', 'Gradio'] })]);
        const links = [...document.querySelectorAll('.change-added a')];

        expect(links.map(a => a.textContent)).toEqual(['Kedro', 'Gradio']);
        expect(links[0].getAttribute('href')).toBe('/agent/Kedro');
    });

    it('escapes a name that needs it', async () => {
        await boot([entry({ added: ['ROS 2 Thing'] })]);
        expect(document.querySelector('.change-added a').getAttribute('href'))
            .toBe('/agent/ROS%202%20Thing');
    });

    it('lists removals separately from additions', async () => {
        await boot([entry({ added: ['New'], removed: ['Gone'] })]);

        expect(document.querySelector('.change-added').textContent).toContain('New');
        expect(document.querySelector('.change-removed').textContent).toContain('Gone');
    });

    it('summarises edits by field rather than dumping the text', async () => {
        await boot([entry({
            edited: [{ name: 'Cursor', fields: [{ field: 'description', from: 'a', to: 'b' }] }],
        })]);

        const text = document.querySelector('.change-edited').textContent;
        expect(text).toContain('Cursor');
        expect(text).toContain('description');
        expect(text).not.toContain('from');
    });

    it('counts the agents when several were edited at once', async () => {
        await boot([entry({
            edited: [
                { name: 'A', fields: [{ field: 'status', from: 'active', to: 'archived' }] },
                { name: 'B', fields: [{ field: 'status', from: 'active', to: 'dormant' }] },
            ],
        })]);

        expect(document.querySelector('.change-edited').textContent).toContain('2 agents');
    });

    it('shows nothing for a section with no changes', async () => {
        await boot([entry()]);
        expect(document.querySelectorAll('.change-list li')).toHaveLength(0);
    });
});

describe('when there is nothing to show', () => {
    it('explains how to build the history', async () => {
        await boot([]);
        expect(document.getElementById('changesArea').textContent).toContain('changelog.py');
    });

    it('reports a failure rather than staying blank', async () => {
        stubFetch({ '/api/changelog': { ok: false, status: 500, body: {} } });
        bootPage({ html: CHANGES_HTML, script: 'changes.js',
                   extraScripts: scriptsFor('changes.html', 'changes.js') });
        await flush();

        expect(document.getElementById('changesArea').textContent).toContain('Could not load');
    });
});
