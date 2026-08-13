import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { CATEGORY_HTML, bootPage, flush, scriptsFor, stubFetch } from './helpers.js';

function agent(name, category = 'Evaluation') {
    return { name, metadata: { name, category, stack: 'Python', stars: 100, description: `${name} does things.`, url: 'https://example.com' } };
}

function routes(overrides = {}) {
    return {
        '/api/agents': { body: { agents: [agent('Ragas'), agent('DeepEval')], metadata: { total: 2 } } },
        '/api/categories': { body: [{ name: 'Evaluation', count: 2 }, { name: 'Safety', count: 5 }] },
        ...overrides,
    };
}

async function boot(path = '/category/Evaluation', r = routes()) {
    window.history.replaceState({}, '', path);
    const calls = stubFetch(r);
    bootPage({ html: CATEGORY_HTML, script: 'category.js',
               extraScripts: scriptsFor('category.html', 'category.js') });
    await flush();
    return calls;
}

beforeEach(() => window.history.replaceState({}, '', '/'));
afterEach(() => { delete globalThis.fetch; });

describe('browsing a category', () => {
    it('requests only that category, most starred first', async () => {
        const calls = await boot();
        const call = calls.find(c => c.url.includes('/api/agents'));
        expect(decodeURIComponent(call.url)).toContain('category=Evaluation');
        expect(call.url).toContain('sort=stars');
    });

    it('renders the agents', async () => {
        await boot();
        const names = [...document.querySelectorAll('.agent-name')].map(n => n.textContent);
        expect(names).toEqual(['Ragas', 'DeepEval']);
    });

    it('reports how many there are', async () => {
        await boot();
        expect(document.getElementById('categoryCount').textContent).toContain('2 agents');
    });

    it('uses the singular for one agent', async () => {
        await boot('/category/Evaluation', routes({
            '/api/agents': { body: { agents: [agent('Ragas')], metadata: { total: 1 } } },
        }));
        expect(document.getElementById('categoryCount').textContent).toContain('1 agent,');
    });

    it('decodes a category with a space', async () => {
        const calls = await boot('/category/Code%20Generation');
        // URLSearchParams encodes a space as "+", which is valid in a query.
        expect(calls.find(c => c.url.includes('/api/agents')).url)
            .toContain('category=Code+Generation');
    });

    it('clears aria-busy when done', async () => {
        await boot();
        expect(document.getElementById('categoryGrid').getAttribute('aria-busy')).toBe('false');
    });
});

describe('navigating between categories', () => {
    it('links to the other categories', async () => {
        await boot();
        const links = [...document.querySelectorAll('#categoryOther a')];
        expect(links.map(a => a.textContent)).toEqual(['Safety (5)']);
        expect(links[0].getAttribute('href')).toBe('/category/Safety');
    });

    it('does not link to itself', async () => {
        await boot();
        const hrefs = [...document.querySelectorAll('#categoryOther a')].map(a => a.getAttribute('href'));
        expect(hrefs).not.toContain('/category/Evaluation');
    });
});

describe('empty and error states', () => {
    it('says so when the category is empty', async () => {
        await boot('/category/Nothing', routes({
            '/api/agents': { body: { agents: [], metadata: { total: 0 } } },
        }));
        expect(document.getElementById('categoryGrid').textContent).toContain('Nothing is filed under');
    });

    it('reports a failure', async () => {
        await boot('/category/Evaluation', routes({
            '/api/agents': { ok: false, status: 500, body: {} },
        }));
        expect(document.getElementById('categoryGrid').textContent).toContain('Could not load');
    });

    it('handles a path with no category', async () => {
        await boot('/');
        expect(document.getElementById('categoryGrid').textContent).toContain('No category specified');
    });
});

describe('robustness', () => {
    it('reports the whole category size, not the page size', async () => {
        await boot('/category/Evaluation', routes({
            '/api/agents': { body: { agents: [agent('Ragas')], metadata: { total: 40 } } },
        }));
        expect(document.getElementById('categoryCount').textContent).toContain('40 agents');
    });

    it('survives a malformed percent escape in the path', async () => {
        await boot('/category/100%', routes({
            '/api/agents': { body: { agents: [], metadata: { total: 0 } } },
        }));
        expect(document.getElementById('categoryGrid').getAttribute('aria-busy')).toBe('false');
        expect(document.getElementById('categoryCount').textContent).not.toContain('Loading');
    });

    it('does not leave the header on Loading after a failure', async () => {
        await boot('/category/Evaluation', routes({
            '/api/agents': { ok: false, status: 500, body: {} },
        }));
        expect(document.getElementById('categoryCount').textContent).not.toContain('Loading');
    });

    it('clears the header for an empty category', async () => {
        await boot('/category/Nothing', routes({
            '/api/agents': { body: { agents: [], metadata: { total: 0 } } },
        }));
        expect(document.getElementById('categoryCount').textContent).toContain('No agents');
    });
});
