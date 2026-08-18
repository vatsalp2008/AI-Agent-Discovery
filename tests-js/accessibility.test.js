/**
 * Every interactive control must have an accessible name, including the ones
 * created in JavaScript after the page loads — which the server-rendered
 * markup checks cannot see.
 */

import { afterEach, describe, expect, it } from 'vitest';

import {
    ADMIN_HTML, AGENT_HTML, bootPage, COLLECTIONS_HTML, COMPARE_HTML,
    CHANGES_HTML, DASHBOARD_HTML, flush, SAVED_HTML, SEARCH_HTML, scriptsFor,
    stubFetch, SUBMIT_HTML, TECH_HTML, TECH_INDEX_HTML,
} from './helpers.js';

/** The name a screen reader would announce for `el`. */
function accessibleName(el) {
    const aria = el.getAttribute('aria-label');
    if (aria && aria.trim()) return aria.trim();

    const labelledBy = el.getAttribute('aria-labelledby');
    if (labelledBy) {
        const target = document.getElementById(labelledBy);
        if (target && target.textContent.trim()) return target.textContent.trim();
    }

    if (el.id) {
        const label = document.querySelector(`label[for="${el.id}"]`);
        if (label && label.textContent.trim()) return label.textContent.trim();
    }
    if (el.closest && el.closest('label')) return 'wrapped in a label';

    if (el.title && el.title.trim()) return el.title.trim();

    // Visible text counts as a name only if it is actually words. A control
    // labelled "×" or "↑" announces as "multiplication sign" / "upwards
    // arrow", which tells a screen reader user nothing — those need an
    // explicit aria-label.
    const text = (el.textContent || '').trim();
    return /[a-z0-9]/i.test(text) ? text : '';
}

function unnamedControls() {
    const selector = 'button, a[href], input:not([type=hidden]), select, textarea';
    return [...document.querySelectorAll(selector)]
        .filter(el => !accessibleName(el))
        .map(el => `${el.tagName.toLowerCase()}${el.id ? '#' + el.id : ''}${el.className ? '.' + String(el.className).split(' ')[0] : ''}`);
}

function agent(name) {
    return {
        name,
        metadata: { name, category: 'Automation', stack: 'Python,Git', stars: 100, description: `${name} does things.`, url: 'https://example.com' },
    };
}

afterEach(() => { delete globalThis.fetch; });

describe('rendered controls have accessible names', () => {
    it('search page, with results', async () => {
        stubFetch({
            '/api/categories': { body: [{ name: 'Automation', count: 3 }] },
            '/api/agents': { body: { agents: [agent('Aider')], metadata: { total: 1, has_more: false } } },
            '/api/search': { body: { results: [agent('Aider'), agent('Cursor')], metadata: { confident: true } } },
        });
        bootPage({
            html: SEARCH_HTML,
            script: 'main.js',
            // Taken from the template, so adding a dependency cannot leave
            // this booting an incomplete page.
            extraScripts: scriptsFor('index.html', 'main.js'),
        });
        await flush();

        document.getElementById('searchInput').value = 'x';
        document.getElementById('searchForm').dispatchEvent(
            new window.Event('submit', { bubbles: true, cancelable: true }));
        await flush();

        expect(unnamedControls()).toEqual([]);
    });

    it('dashboard, with a loaded page of agents', async () => {
        stubFetch({
            '/api/stats': { body: { count: 2, top_category: { name: 'Automation' }, total_stars: 10 } },
            '/api/categories': { body: [{ name: 'Automation', count: 2 }] },
            '/api/tech': { body: [{ name: 'Python', count: 2 }] },
            '/api/agents': { body: { agents: [agent('Aider')], metadata: { total: 2, has_more: true } } },
        });
        bootPage({
            html: DASHBOARD_HTML,
            script: 'dashboard.js',
            extraScripts: scriptsFor('dashboard.html', 'dashboard.js'),
        });
        await flush();
        expect(unnamedControls()).toEqual([]);
    });

    it('comparison table', async () => {
        window.history.replaceState({}, '', '/compare?names=Aider,Cursor');
        stubFetch({
            '/api/agents?': { body: { agents: [agent('Aider')], metadata: {} } },
            '/api/compare': { body: { agents: [agent('Aider'), agent('Cursor')], metadata: { missing: [] } } },
        });
        bootPage({ html: COMPARE_HTML, script: 'compare.js' });
        await flush();
        expect(unnamedControls()).toEqual([]);
    });

    it('collections, with a populated collection', async () => {
        localStorage.clear();
        bootPage({
            html: COLLECTIONS_HTML,
            script: 'collections-page.js',
            extraScripts: [{ file: 'collections.js', global: 'Collections' }],
        });
        globalThis.Collections.create('Coding');
        globalThis.Collections.add('Coding', 'Aider');
        globalThis.Collections.add('Coding', 'Cursor');
        bootPage({
            html: COLLECTIONS_HTML,
            script: 'collections-page.js',
            extraScripts: [{ file: 'collections.js', global: 'Collections' }],
        });
        expect(unnamedControls()).toEqual([]);
        localStorage.clear();
    });

    it('catalogue editor, with rows', async () => {
        stubFetch({
            '/api/admin/status': { body: { enabled: true, total: 1, catalogue_stale: false } },
            '/api/agents': { body: { agents: [agent('Aider')], metadata: {} } },
        });
        bootPage({ html: ADMIN_HTML, script: 'admin.js' });
        await flush();
        expect(unnamedControls()).toEqual([]);
    });

    it('agent detail page', async () => {
        window.history.replaceState({}, '', '/agent/Aider');
        stubFetch({
            '/similar': { body: { agents: [agent('Cursor')], metadata: {} } },
            '/api/agents/': { body: agent('Aider') },
        });
        bootPage({ html: AGENT_HTML, script: 'agent.js' });
        await flush();
        expect(unnamedControls()).toEqual([]);
    });

    it('saved searches, with entries', async () => {
        localStorage.setItem('agentdiscovery:saved-searches', JSON.stringify([
            { query: 'run a model locally', category: '',
              snapshot: { names: ['Ollama'], stars: { Ollama: 100 }, at: new Date().toISOString() } },
        ]));
        stubFetch({ '/api/search': { body: { results: [], metadata: {} } } });
        bootPage({
            html: SAVED_HTML,
            script: 'saved-page.js',
            extraScripts: scriptsFor('saved.html', 'saved-page.js'),
        });
        await flush();
        expect(unnamedControls()).toEqual([]);
    });

    it('search page with the health toggle', async () => {
        stubFetch({
            '/api/categories': { body: [{ name: 'Automation', count: 3 }] },
            '/api/agents': { body: { agents: [agent('Ollama')], metadata: {} } },
        });
        bootPage({ html: SEARCH_HTML, script: 'main.js',
                   extraScripts: scriptsFor('index.html', 'main.js') });
        await flush();
        expect(unnamedControls()).toEqual([]);
    });

    it('technology index, with a filter', async () => {
        stubFetch({ '/api/tech': { body: [{ name: 'Python', count: 9 },
                                          { name: 'Zig', count: 1 }] } });
        bootPage({ html: TECH_INDEX_HTML, script: 'tech-index.js',
                   extraScripts: scriptsFor('tech-index.html', 'tech-index.js') });
        await flush();
        expect(unnamedControls()).toEqual([]);
    });

    it('technology page, with results', async () => {
        window.history.replaceState({}, '', '/tech/Python');
        stubFetch({
            '/api/tech': { body: [{ name: 'Python', count: 9 }, { name: 'Rust', count: 2 }] },
            '/api/agents?': { body: { agents: [agent('Ollama')], metadata: { total: 1 } } },
        });
        bootPage({ html: TECH_HTML, script: 'tech.js',
                   extraScripts: scriptsFor('tech.html', 'tech.js') });
        await flush();
        expect(unnamedControls()).toEqual([]);
    });

    it('change history, with entries', async () => {
        stubFetch({
            '/api/changelog': { body: { entries: [{
                commit: 'abc', at: '2026-08-14T00:00:00+00:00', subject: 'Add agents',
                total: 223, added: ['Kedro'], removed: ['Gone'],
                edited: [{ name: 'Cursor', fields: [{ field: 'category' }] }],
            }], metadata: {} } },
        });
        bootPage({ html: CHANGES_HTML, script: 'changes.js',
                   extraScripts: scriptsFor('changes.html', 'changes.js') });
        await flush();
        expect(unnamedControls()).toEqual([]);
    });

    it('submission form', async () => {
        stubFetch({ '/api/categories': { body: [{ name: 'Automation', count: 3 }] } });
        bootPage({ html: SUBMIT_HTML, script: 'submit.js' });
        await flush();
        expect(unnamedControls()).toEqual([]);
    });
});

