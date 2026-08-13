/**
 * Wiring tests for dashboard.js. The pure helpers live in dashboard-stats.js
 * and are covered separately.
 */

import { afterEach, describe, expect, it } from 'vitest';

import { DASHBOARD_HTML, bootPage, flush, scriptsFor, stubFetch } from './helpers.js';

const STATS = {
    count: 37,
    categories: 8,
    top_category: { name: 'Code Generation', count: 9 },
    total_stars: 653000,
};

function agent(name) {
    return {
        name,
        description: `${name} description.`,
        metadata: { name, category: 'Code Generation', stack: 'Python', stars: 1000, description: `${name} d.` },
    };
}

function page(names, { total = names.length, hasMore = false } = {}) {
    return { body: { agents: names.map(agent), metadata: { total, count: names.length, has_more: hasMore } } };
}

async function boot(routes) {
    const calls = stubFetch(routes);
    bootPage({
        html: DASHBOARD_HTML,
        script: 'dashboard.js',
        extraScripts: scriptsFor('dashboard.html', 'dashboard.js'),
    });
    await flush();
    return calls;
}

afterEach(() => {
    delete globalThis.fetch;
});

describe('stats tiles', () => {
    it('fills the tiles from /api/stats', async () => {
        await boot({ '/api/stats': { body: STATS }, '/api/agents': page(['Aider']) });
        expect(document.getElementById('totalAgents').textContent).toBe('37');
        expect(document.getElementById('topCategory').textContent).toBe('Code Generation');
        expect(document.getElementById('totalStars').textContent).toBe('653.0k');
    });

    it('does not download every agent just to compute totals', async () => {
        const calls = await boot({ '/api/stats': { body: STATS }, '/api/agents': page(['Aider'], { total: 37, hasMore: true }) });
        const agentsCall = calls.find(c => c.url.includes('/api/agents'));
        expect(agentsCall.url).toContain('limit=');
    });

    it('still renders the grid when stats fail', async () => {
        await boot({
            '/api/stats': { ok: false, status: 500, body: {} },
            '/api/agents': page(['Aider']),
        });
        expect(document.querySelectorAll('.agent-card')).toHaveLength(1);
    });

    it('clears aria-busy on the stats grid', async () => {
        await boot({ '/api/stats': { body: STATS }, '/api/agents': page(['Aider']) });
        expect(document.getElementById('statsGrid').getAttribute('aria-busy')).toBe('false');
    });
});

describe('paging', () => {
    it('offers Load more when pages remain', async () => {
        await boot({ '/api/stats': { body: STATS }, '/api/agents': page(['Aider'], { total: 3, hasMore: true }) });
        const button = document.querySelector('.load-more');
        expect(button).not.toBeNull();
        expect(button.textContent).toContain('1 of 3');
    });

    it('appends the next page without discarding the first', async () => {
        let call = 0;
        await boot({
            '/api/stats': { body: STATS },
            '/api/agents': () => {
                call += 1;
                return call === 1
                    ? page(['Aider'], { total: 2, hasMore: true })
                    : page(['Cursor'], { total: 2, hasMore: false });
            },
        });

        document.querySelector('.load-more').click();
        await flush();

        const names = [...document.querySelectorAll('.agent-name')].map(n => n.textContent);
        expect(names).toEqual(['Aider', 'Cursor']);
    });

    it('requests the next page with the right offset', async () => {
        let call = 0;
        const calls = await boot({
            '/api/stats': { body: STATS },
            '/api/agents': () => {
                call += 1;
                return call === 1
                    ? page(['A', 'B'], { total: 4, hasMore: true })
                    : page(['C', 'D'], { total: 4, hasMore: false });
            },
        });

        document.querySelector('.load-more').click();
        await flush();

        const agentCalls = calls.filter(c => c.url.includes('/api/agents'));
        expect(agentCalls[0].url).toContain('offset=0');
        expect(agentCalls[1].url).toContain('offset=2');
    });

    it('reports completion when every agent is shown', async () => {
        await boot({ '/api/stats': { body: STATS }, '/api/agents': page(['Aider'], { total: 1, hasMore: false }) });
        expect(document.querySelector('.load-more')).toBeNull();
        expect(document.getElementById('gridFooter').textContent).toContain('all 1');
    });

    it('offers a retry when a page fails to load', async () => {
        let call = 0;
        await boot({
            '/api/stats': { body: STATS },
            '/api/agents': () => {
                call += 1;
                return call === 1 ? page(['Aider'], { total: 2, hasMore: true }) : { ok: false, status: 500, body: {} };
            },
        });

        document.querySelector('.load-more').click();
        await flush();

        const button = document.querySelector('.load-more');
        expect(button.textContent).toBe('Retry');
        expect(button.disabled).toBe(false);
    });
});

describe('empty and error states', () => {
    it('tells the user to seed an empty index', async () => {
        await boot({ '/api/stats': { body: { count: 0, top_category: null, total_stars: 0 } }, '/api/agents': page([]) });
        expect(document.getElementById('allAgentsGrid').textContent).toContain('seed.py');
    });

    it('reports a failure to load the grid', async () => {
        await boot({ '/api/stats': { body: STATS }, '/api/agents': { ok: false, status: 500, body: {} } });
        expect(document.querySelector('.result-message.error').textContent).toContain('Error loading');
    });

    it('does not leave aria-busy stuck on after an error', async () => {
        await boot({ '/api/stats': { body: STATS }, '/api/agents': { ok: false, status: 500, body: {} } });
        expect(document.getElementById('allAgentsGrid').getAttribute('aria-busy')).toBe('false');
    });
});

describe('filter and sort controls', () => {
    function withFacets(overrides = {}) {
        return {
            '/api/stats': { body: STATS },
            '/api/categories': { body: [{ name: 'Code Generation', count: 9 }] },
            '/api/tech': { body: [{ name: 'Python', count: 26 }] },
            '/api/agents': page(['Aider']),
            ...overrides,
        };
    }

    it('populates the category and tech selects from the facet endpoints', async () => {
        await boot(withFacets());
        await flush();
        expect([...document.querySelectorAll('#filterCategory option')].map(o => o.value))
            .toEqual(['', 'Code Generation']);
        expect([...document.querySelectorAll('#filterTech option')].map(o => o.value))
            .toEqual(['', 'Python']);
    });

    it('sends the selected category to the API', async () => {
        const calls = await boot(withFacets());
        await flush();
        document.getElementById('filterCategory').value = 'Code Generation';
        document.getElementById('filterCategory').dispatchEvent(new window.Event('change'));
        await flush();

        const last = calls.filter(c => c.url.includes('/api/agents')).pop();
        expect(last.url).toContain('category=Code+Generation');
        expect(last.url).toContain('offset=0');
    });

    it('sends the chosen sort key', async () => {
        const calls = await boot(withFacets());
        await flush();
        document.getElementById('sortBy').value = 'stars';
        document.getElementById('sortBy').dispatchEvent(new window.Event('change'));
        await flush();
        expect(calls.filter(c => c.url.includes('/api/agents')).pop().url).toContain('sort=stars');
    });

    it('reverses the order and updates the button', async () => {
        const calls = await boot(withFacets());
        await flush();
        const button = document.getElementById('sortOrder');
        button.click();
        await flush();

        expect(button.textContent).toBe('↓');
        expect(button.getAttribute('aria-label')).toContain('descending');
        expect(calls.filter(c => c.url.includes('/api/agents')).pop().url).toContain('order=desc');
    });

    it('debounces typing rather than firing per keystroke', async () => {
        const calls = await boot(withFacets());
        await flush();
        const before = calls.filter(c => c.url.includes('/api/agents')).length;

        const input = document.getElementById('filterQuery');
        for (const value of ['c', 'cu', 'cur']) {
            input.value = value;
            input.dispatchEvent(new window.Event('input'));
        }
        await new Promise(r => setTimeout(r, 400));
        await flush();

        const after = calls.filter(c => c.url.includes('/api/agents')).length;
        expect(after - before).toBe(1);
        expect(calls.filter(c => c.url.includes('/api/agents')).pop().url).toContain('q=cur');
    });

    it('omits empty filters from the query', async () => {
        const calls = await boot(withFacets());
        const url = calls.find(c => c.url.includes('/api/agents')).url;
        expect(url).not.toContain('q=');
        expect(url).not.toContain('category=');
    });

    it('reports when filters match nothing', async () => {
        let call = 0;
        await boot(withFacets({
            '/api/agents': () => {
                call += 1;
                return call === 1 ? page(['Aider']) : page([], { total: 0 });
            },
        }));
        await flush();
        document.getElementById('sortBy').dispatchEvent(new window.Event('change'));
        await flush();
        expect(document.getElementById('allAgentsGrid').textContent).toContain('No agents match');
    });
});

describe('category tiles', () => {
    it('links each category to its browse page', async () => {
        await boot({
            '/api/stats': { body: STATS },
            '/api/categories': { body: [{ name: 'Evaluation', count: 8 }, { name: 'Safety', count: 6 }] },
            '/api/tech': { body: [] },
            '/api/agents': page(['Aider']),
        });
        await flush();

        const tiles = [...document.querySelectorAll('.category-tile')];
        expect(tiles.map(t => t.getAttribute('href')))
            .toEqual(['/category/Evaluation', '/category/Safety']);
        expect(tiles[0].textContent).toContain('8 agents');
    });

    it('uses the singular for one agent', async () => {
        await boot({
            '/api/stats': { body: STATS },
            '/api/categories': { body: [{ name: 'Solo', count: 1 }] },
            '/api/tech': { body: [] },
            '/api/agents': page(['Aider']),
        });
        await flush();
        expect(document.querySelector('.category-tile').textContent).toContain('1 agent');
    });

    it('encodes a category with a space', async () => {
        await boot({
            '/api/stats': { body: STATS },
            '/api/categories': { body: [{ name: 'Code Generation', count: 3 }] },
            '/api/tech': { body: [] },
            '/api/agents': page(['Aider']),
        });
        await flush();
        expect(document.querySelector('.category-tile').getAttribute('href'))
            .toBe('/category/Code%20Generation');
    });

    it('does not break the page when categories fail to load', async () => {
        await boot({
            '/api/stats': { body: STATS },
            '/api/categories': { ok: false, status: 500, body: {} },
            '/api/tech': { body: [] },
            '/api/agents': page(['Aider']),
        });
        await flush();
        expect(document.querySelectorAll('.agent-card').length).toBeGreaterThan(0);
    });
});
