import { beforeAll, describe, expect, it } from 'vitest';

import { loadScript } from './helpers.js';

let Api;

beforeAll(() => { Api = loadScript('agents-api.js', 'AgentsApi'); });

/** A fetch stub returning `pages` in order. */
function paged(pages) {
    const urls = [];
    let index = 0;
    const fetchImpl = (url) => {
        urls.push(url);
        const page = pages[Math.min(index, pages.length - 1)];
        index += 1;
        if (page instanceof Error) return Promise.reject(page);
        return Promise.resolve({
            ok: page.ok !== false,
            status: page.status || 200,
            json: () => Promise.resolve(page.body),
        });
    };
    return { fetchImpl, urls };
}

function page(names, hasMore, total) {
    return { body: { agents: names.map(name => ({ name })), metadata: { has_more: hasMore, total } } };
}

describe('query building', () => {
    it('omits empty values', () => {
        expect(Api.query({ category: '', sort: 'name' }, { limit: 200 }))
            .toBe('sort=name&limit=200');
    });

    it('encodes values', () => {
        expect(Api.query({ category: 'Code Generation' })).toContain('Code+Generation');
    });

    it('lets extras override', () => {
        expect(Api.query({ limit: 5 }, { limit: 200 })).toBe('limit=200');
    });
});

describe('fetching every page', () => {
    it('returns a single page unchanged', async () => {
        const { fetchImpl, urls } = paged([page(['A'], false, 1)]);
        const result = await Api.fetchAll({}, { fetchImpl });
        expect(result.agents.map(a => a.name)).toEqual(['A']);
        expect(urls).toHaveLength(1);
    });

    it('follows has_more across pages', async () => {
        const { fetchImpl, urls } = paged([
            page(['A'], true, 3), page(['B'], true, 3), page(['C'], false, 3),
        ]);
        const result = await Api.fetchAll({}, { fetchImpl });
        expect(result.agents.map(a => a.name)).toEqual(['A', 'B', 'C']);
        expect(urls).toHaveLength(3);
    });

    it('advances the offset by what it received', async () => {
        const { fetchImpl, urls } = paged([page(['A', 'B'], true, 3), page(['C'], false, 3)]);
        await Api.fetchAll({}, { fetchImpl });
        expect(urls[0]).toContain('offset=0');
        expect(urls[1]).toContain('offset=2');
    });

    it('passes the caller filters through', async () => {
        const { fetchImpl, urls } = paged([page(['A'], false, 1)]);
        await Api.fetchAll({ category: 'Robotics', sort: 'stars' }, { fetchImpl });
        expect(urls[0]).toContain('category=Robotics');
        expect(urls[0]).toContain('sort=stars');
    });

    it('reports the server total, not the page count', async () => {
        const { fetchImpl } = paged([page(['A'], false, 512)]);
        expect((await Api.fetchAll({}, { fetchImpl })).total).toBe(512);
    });
});

describe('when a page fails', () => {
    it('keeps what arrived before a network error', async () => {
        const { fetchImpl } = paged([page(['A'], true, 2), new Error('offline')]);
        expect((await Api.fetchAll({}, { fetchImpl })).agents.map(a => a.name)).toEqual(['A']);
    });

    it('keeps what arrived before an error status', async () => {
        const { fetchImpl } = paged([page(['A'], true, 2), { ok: false, status: 500, body: {} }]);
        expect((await Api.fetchAll({}, { fetchImpl })).agents.map(a => a.name)).toEqual(['A']);
    });

    it('returns nothing when the first page fails', async () => {
        const { fetchImpl } = paged([new Error('offline')]);
        const result = await Api.fetchAll({}, { fetchImpl });
        expect(result.agents).toEqual([]);
        expect(result.total).toBe(0);
    });

    it('stops if has_more never clears', async () => {
        const { fetchImpl, urls } = paged([page(['A'], true, 999)]);
        await Api.fetchAll({}, { fetchImpl });
        expect(urls).toHaveLength(Api.MAX_PAGES);
    });

    it('stops on an empty page even if has_more is set', async () => {
        const { fetchImpl, urls } = paged([page([], true, 0)]);
        await Api.fetchAll({}, { fetchImpl });
        expect(urls).toHaveLength(1);
    });
});

describe('signalling failure', () => {
    it('flags a partial result', async () => {
        const { fetchImpl } = paged([page(['A'], true, 2), new Error('offline')]);
        const result = await Api.fetchAll({}, { fetchImpl });
        expect(result.failed).toBe(true);
        expect(result.agents).toHaveLength(1);
    });

    it('does not flag a complete result', async () => {
        const { fetchImpl } = paged([page(['A'], false, 1)]);
        expect((await Api.fetchAll({}, { fetchImpl })).failed).toBe(false);
    });

    it('flags an empty result that failed, so it is not read as "nothing here"', async () => {
        const { fetchImpl } = paged([{ ok: false, status: 500, body: {} }]);
        const result = await Api.fetchAll({}, { fetchImpl });
        expect(result.agents).toEqual([]);
        expect(result.failed).toBe(true);
    });

    it('does not flag a genuinely empty catalogue', async () => {
        const { fetchImpl } = paged([page([], false, 0)]);
        const result = await Api.fetchAll({}, { fetchImpl });
        expect(result.agents).toEqual([]);
        expect(result.failed).toBe(false);
    });
});
