import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { bootPage, flush, SAVED_HTML, scriptsFor, stubFetch } from './helpers.js';

function searchBody(...agents) {
    return {
        results: agents.map(([name, stars]) => ({
            name,
            metadata: { name, stars, category: 'Automation', description: `${name} does things.` },
        })),
        metadata: {},
    };
}

function boot(routes = {}) {
    const calls = stubFetch({ '/api/search': { body: searchBody(['Ollama', 100]) }, ...routes });
    bootPage({
        html: SAVED_HTML,
        script: 'saved-page.js',
        extraScripts: scriptsFor('saved.html', 'saved-page.js'),
    });
    return calls;
}

/** Save a search directly, the way the search page would. */
function save(query, agents, category = '') {
    globalThis.SavedSearches.save(query, category,
        agents.map(([name, stars]) => ({ name, metadata: { name, stars } })));
}

beforeEach(() => localStorage.clear());
afterEach(() => { delete globalThis.fetch; });

describe('the empty state', () => {
    it('explains how to save one', async () => {
        boot();
        await flush();
        expect(document.getElementById('savedArea').textContent).toContain('No saved searches yet');
    });

    it('disables the controls that would do nothing', async () => {
        boot();
        await flush();
        expect(document.getElementById('checkAll').disabled).toBe(true);
        expect(document.getElementById('clearSaved').disabled).toBe(true);
    });
});

describe('listing saved searches', () => {
    it('shows each one', async () => {
        boot();
        save('run a model locally', [['Ollama', 100]]);
        save('edit code', [['Aider', 200]]);
        window.SavedPage.render();

        const headings = [...document.querySelectorAll('.saved-card h2')].map(h => h.textContent);
        expect(headings).toEqual(['edit code', 'run a model locally']);
    });

    it('links back to the search that produced it', async () => {
        boot();
        save('run a model', [['Ollama', 100]]);
        window.SavedPage.render();

        const href = document.querySelector('.saved-card h2 a').getAttribute('href');
        expect(href).toContain('q=run+a+model');
    });

    it('carries the category filter into the link', async () => {
        boot();
        globalThis.SavedSearches.save('agents', 'Robotics', [{ name: 'A', metadata: { name: 'A' } }]);
        window.SavedPage.render();

        expect(document.querySelector('.saved-card h2 a').getAttribute('href'))
            .toContain('category=Robotics');
    });

    it('says how many results it had when saved', async () => {
        boot();
        save('q', [['A', 1], ['B', 2]]);
        window.SavedPage.render();

        expect(document.querySelector('.saved-meta').textContent).toContain('2 result(s)');
    });
});

describe('checking for changes', () => {
    it('reports an agent that now matches', async () => {
        boot({ '/api/search': { body: searchBody(['Ollama', 100], ['MLX', 50]) } });
        save('run a model', [['Ollama', 100]]);
        window.SavedPage.render();

        document.querySelector('.saved-card button').click();
        await flush();

        expect(document.querySelector('.saved-changes').textContent).toContain('New: MLX');
    });

    it('reports an agent that dropped out', async () => {
        boot({ '/api/search': { body: searchBody(['Ollama', 100]) } });
        save('run a model', [['Ollama', 100], ['MLX', 50]]);
        window.SavedPage.render();

        document.querySelector('.saved-card button').click();
        await flush();

        expect(document.querySelector('.saved-changes').textContent).toContain('No longer matches: MLX');
    });

    it('reports momentum with the direction spelled out, not just coloured', async () => {
        boot({ '/api/search': { body: searchBody(['Ollama', 400]) } });
        save('run a model', [['Ollama', 100]]);
        window.SavedPage.render();

        document.querySelector('.saved-card button').click();
        await flush();

        const text = document.querySelector('.saved-changes').textContent;
        expect(text).toContain('100');
        expect(text).toContain('400');
        expect(text).toMatch(/↑|↓/);
    });

    it('says so when nothing moved', async () => {
        boot({ '/api/search': { body: searchBody(['Ollama', 100]) } });
        save('run a model', [['Ollama', 100]]);
        window.SavedPage.render();

        document.querySelector('.saved-card button').click();
        await flush();

        expect(document.querySelector('.saved-changes').textContent).toContain('No change');
    });

    it('does not report the same change twice', async () => {
        /** The check adopts the fresh results, so a second check compares
         *  against what was last seen rather than the original save. */
        boot({ '/api/search': { body: searchBody(['Ollama', 100], ['MLX', 50]) } });
        save('run a model', [['Ollama', 100]]);
        window.SavedPage.render();

        document.querySelector('.saved-card button').click();
        await flush();
        expect(document.querySelector('.saved-changes').textContent).toContain('New: MLX');

        document.querySelector('.saved-card button').click();
        await flush();
        expect(document.querySelector('.saved-changes').textContent).toContain('No change');
    });

    it('passes the category filter to the API', async () => {
        const calls = boot();
        globalThis.SavedSearches.save('agents', 'Robotics', [{ name: 'A', metadata: { name: 'A' } }]);
        window.SavedPage.render();

        document.querySelector('.saved-card button').click();
        await flush();

        expect(calls.some(c => c.url.includes('category=Robotics'))).toBe(true);
    });

    it('reports a rate limit in words a person can act on', async () => {
        boot({ '/api/search': { ok: false, status: 429, body: { error: 'slow down' } } });
        save('q', [['A', 1]]);
        window.SavedPage.render();

        document.querySelector('.saved-card button').click();
        await flush();

        expect(document.querySelector('.saved-changes').textContent).toContain('Too many searches');
    });

    it('a failure on one search does not blank the others', async () => {
        boot({ '/api/search': { ok: false, status: 500, body: {} } });
        save('one', [['A', 1]]);
        save('two', [['B', 2]]);
        window.SavedPage.render();

        document.getElementById('checkAll').click();
        await flush();

        expect(document.querySelectorAll('.saved-card')).toHaveLength(2);
        expect(document.getElementById('savedResult').textContent).toContain('Could not check');
    });

    it('checks every saved search in one go', async () => {
        const calls = boot();
        save('one', [['A', 1]]);
        save('two', [['B', 2]]);
        window.SavedPage.render();

        document.getElementById('checkAll').click();
        await flush();

        expect(calls.filter(c => c.url.includes('/api/search'))).toHaveLength(2);
    });

    it('re-enables the button after checking', async () => {
        boot();
        save('one', [['A', 1]]);
        window.SavedPage.render();

        document.getElementById('checkAll').click();
        await flush();

        expect(document.getElementById('checkAll').disabled).toBe(false);
        expect(document.getElementById('checkAll').textContent).toBe('Check for changes');
    });

    it('a search saved before results were recorded becomes the baseline', async () => {
        boot({ '/api/search': { body: searchBody(['Ollama', 100]) } });
        localStorage.setItem('agentdiscovery:saved-searches',
            JSON.stringify([{ query: 'old', category: '' }]));
        window.SavedPage.render();

        document.querySelector('.saved-card button').click();
        await flush();

        const text = document.querySelector('.saved-changes').textContent;
        expect(text).toContain('baseline');
        expect(text).not.toContain('New:');
    });
});

describe('removing', () => {
    it('removes one and leaves the rest', async () => {
        boot();
        save('keep', [['A', 1]]);
        save('drop', [['B', 2]]);
        window.SavedPage.render();

        const dropCard = [...document.querySelectorAll('.saved-card')]
            .find(c => c.dataset.query === 'drop');
        dropCard.querySelectorAll('button')[1].click();

        expect([...document.querySelectorAll('.saved-card')].map(c => c.dataset.query))
            .toEqual(['keep']);
    });

    it('removes everything', async () => {
        boot();
        save('one', [['A', 1]]);
        save('two', [['B', 2]]);
        window.SavedPage.render();

        document.getElementById('clearSaved').click();

        expect(globalThis.SavedSearches.list()).toEqual([]);
        expect(document.getElementById('savedArea').textContent).toContain('No saved searches yet');
    });
});
