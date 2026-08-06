/**
 * Wiring tests for dashboard.js. The pure helpers live in dashboard-stats.js
 * and are covered separately.
 */

import { afterEach, describe, expect, it } from 'vitest';

import { bootPage, DASHBOARD_HTML, flush, stubFetch } from './helpers.js';

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
        extraScripts: [{ file: 'dashboard-stats.js', global: 'DashboardStats' }],
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
