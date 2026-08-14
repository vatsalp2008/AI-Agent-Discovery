import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { COMPARE_HTML, bootPage, flush, scriptsFor, stubFetch } from './helpers.js';

function agent(name, extra = {}) {
    return {
        name,
        metadata: { name, category: 'Code Generation', stack: 'Python,Git', stars: 1000, description: `${name} does things.`, ...extra },
    };
}

function routes(overrides = {}) {
    return {
        '/api/agents?': { body: { agents: [agent('Aider'), agent('Cursor')], metadata: {} } },
        '/api/compare': { body: { agents: [agent('Aider'), agent('Cursor')], metadata: { requested: 2, count: 2, missing: [] } } },
        ...overrides,
    };
}

async function boot(path = '/compare?names=Aider,Cursor', r = routes()) {
    window.history.replaceState({}, '', path);
    const calls = stubFetch(r);
    bootPage({ html: COMPARE_HTML, script: 'compare.js',
               extraScripts: scriptsFor('compare.html', 'compare.js') });
    await flush();
    return calls;
}

beforeEach(() => window.history.replaceState({}, '', '/compare'));
afterEach(() => { delete globalThis.fetch; });

describe('rendering the comparison', () => {
    it('asks for the agents named in the URL', async () => {
        const calls = await boot();
        const call = calls.find(c => c.url.includes('/api/compare'));
        expect(decodeURIComponent(call.url)).toContain('names=Aider,Cursor');
    });

    it('renders a column per agent and a row per attribute', async () => {
        await boot();
        const headers = [...document.querySelectorAll('.compare-table thead th')].map(t => t.textContent);
        expect(headers[1]).toContain('Aider');
        expect(headers[2]).toContain('Cursor');

        const rows = [...document.querySelectorAll('.compare-table tbody th')].map(t => t.textContent);
        expect(rows).toEqual(['Category', 'GitHub stars', 'Tech stack', 'Description']);
    });

    it('links each column to the agent detail page', async () => {
        await boot();
        const link = document.querySelector('.compare-table thead a');
        expect(link.getAttribute('href')).toBe('/agent/Aider');
    });

    it('prompts when nothing is selected', async () => {
        await boot('/compare');
        expect(document.getElementById('compareArea').textContent).toContain('Pick two or more');
    });

    it('notes agents that were not found', async () => {
        await boot('/compare?names=Aider,Ghost', routes({
            '/api/compare': { body: { agents: [agent('Aider')], metadata: { requested: 2, count: 1, missing: ['Ghost'] } } },
        }));
        expect(document.querySelector('.result-notice').textContent).toContain('Ghost');
        expect(document.querySelector('.compare-table')).not.toBeNull();
    });

    it('reports when none were found', async () => {
        await boot('/compare?names=Ghost', routes({
            '/api/compare': { body: { agents: [], metadata: { requested: 1, count: 0, missing: ['Ghost'] } } },
        }));
        expect(document.getElementById('compareArea').textContent).toContain('None of those agents');
    });

    it('surfaces a server error', async () => {
        await boot('/compare?names=a,b,c,d,e', routes({
            '/api/compare': { ok: false, status: 400, body: { error: "'names' accepts at most 4 agents" } },
        }));
        expect(document.getElementById('compareArea').textContent).toContain('at most 4');
    });

    it('escapes agent-supplied text', async () => {
        await boot('/compare?names=Evil', routes({
            '/api/compare': { body: { agents: [agent('Evil', { description: '<img src=x onerror="globalThis.pwned=1">' })], metadata: { missing: [] } } },
        }));
        expect(document.querySelector('#compareArea img')).toBeNull();
        expect(globalThis.pwned).toBeUndefined();
    });
});

describe('changing the selection', () => {
    it('adding an agent puts it in the URL', async () => {
        await boot('/compare?names=Aider');
        const picker = document.getElementById('comparePick');
        picker.value = 'Cursor';
        picker.dispatchEvent(new window.Event('change'));
        await flush();
        expect(decodeURIComponent(window.location.search)).toContain('names=Aider,Cursor');
    });

    it('refuses to add the same agent twice', async () => {
        await boot('/compare?names=Aider');
        const picker = document.getElementById('comparePick');
        picker.value = 'aider';
        picker.dispatchEvent(new window.Event('change'));
        await flush();
        expect(decodeURIComponent(window.location.search)).toBe('?names=Aider');
    });

    it('removing an agent updates the URL', async () => {
        await boot();
        document.querySelector('.compare-remove').click();
        await flush();
        expect(decodeURIComponent(window.location.search)).toBe('?names=Cursor');
    });

    it('clearing empties the selection', async () => {
        await boot();
        document.getElementById('compareClear').click();
        await flush();
        expect(window.location.search).toBe('');
        expect(document.getElementById('compareArea').textContent).toContain('Pick two or more');
    });

    it('populates the picker from the agent list', async () => {
        await boot();
        const options = [...document.querySelectorAll('#comparePick option')].map(o => o.value);
        expect(options).toEqual(['', 'Aider', 'Cursor']);
    });

    it('groups the picker by category', async () => {
        await boot('/compare?names=Aider', routes({
            '/api/agents?': { body: {
                agents: [
                    agent('Aider', { category: 'Code Generation' }),
                    agent('Ragas', { category: 'Evaluation' }),
                    agent('Cursor', { category: 'Code Generation' }),
                ],
                metadata: {},
            } },
        }));

        const groups = [...document.querySelectorAll('#comparePick optgroup')];
        expect(groups.map(g => g.label)).toEqual(['Code Generation (2)', 'Evaluation (1)']);
        expect([...groups[0].querySelectorAll('option')].map(o => o.value)).toEqual(['Aider', 'Cursor']);
    });

    it('files an agent with no category under Uncategorized', async () => {
        await boot('/compare?names=Aider', routes({
            '/api/agents?': { body: { agents: [{ name: 'Bare', metadata: {} }], metadata: {} } },
        }));
        expect([...document.querySelectorAll('#comparePick optgroup')].map(g => g.label))
            .toEqual(['Uncategorized (1)']);
    });
});

describe('comparing more than a few agents', () => {
    function many(n) {
        return Array.from({ length: n }, (_, i) => agent(`Agent${i}`));
    }

    function bootWith(n) {
        const names = many(n).map(a => a.name).join(',');
        return boot(`/compare?names=${names}`, routes({
            '/api/compare': { body: { agents: many(n), metadata: { count: n, missing: [] } } },
        }));
    }

    it('wraps the table so the later columns are reachable', async () => {
        await bootWith(6);

        const scroll = document.querySelector('.compare-scroll');
        expect(scroll).not.toBeNull();
        expect(scroll.querySelector('.compare-table')).not.toBeNull();
    });

    it('makes the scrollable region keyboard reachable and named', async () => {
        /** A region that scrolls but cannot be focused leaves the later
         *  columns unreadable to anyone not using a mouse. */
        await bootWith(6);

        const scroll = document.querySelector('.compare-scroll');
        expect(scroll.getAttribute('tabindex')).toBe('0');
        expect(scroll.getAttribute('role')).toBe('region');
        expect(scroll.getAttribute('aria-label')).toContain('6');
    });

    it('does not add a focus stop when there is nothing to scroll', async () => {
        await bootWith(2);

        expect(document.querySelector('.compare-scroll')).toBeNull();
        expect(document.querySelector('.compare-table')).not.toBeNull();
    });

    it('still renders one column per agent at eight', async () => {
        await bootWith(8);

        // One label column plus one per agent.
        expect(document.querySelectorAll('.compare-table thead th')).toHaveLength(9);
    });

    it('every agent keeps its remove control', async () => {
        await bootWith(8);
        expect(document.querySelectorAll('.compare-remove')).toHaveLength(8);
    });
});
