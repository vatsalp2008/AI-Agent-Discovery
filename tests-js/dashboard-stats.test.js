import { beforeAll, describe, expect, it } from 'vitest';

import { loadScript } from './helpers.js';

let DashboardStats;

beforeAll(() => {
    DashboardStats = loadScript('dashboard-stats.js', 'DashboardStats');
});

describe('formatTotal', () => {
    it.each([
        [0, '0'],
        [999, '999'],
        [1000, '1.0k'],
        [35000, '35.0k'],
        [933297, '933.3k'],
        [1000000, '1.0M+'],
        [2500000, '2.5M+'],
    ])('formats %s as %s', (input, expected) => {
        expect(DashboardStats.formatTotal(input)).toBe(expected);
    });

    it.each([null, undefined, NaN, 'abc', -5])('returns "0" for %s', (input) => {
        expect(DashboardStats.formatTotal(input)).toBe('0');
    });
});

describe('headline', () => {
    it('reads a full stats payload', () => {
        expect(DashboardStats.headline({
            count: 37,
            top_category: { name: 'Code Generation', count: 11 },
            total_stars: 1234567,
        })).toEqual({ total: '37', topCategory: 'Code Generation', stars: '1.2M+' });
    });

    it('handles an unseeded index', () => {
        expect(DashboardStats.headline({ count: 0, top_category: null, total_stars: 0 }))
            .toEqual({ total: '0', topCategory: 'N/A', stars: '0' });
    });

    it.each([null, undefined, {}])('survives a missing payload (%s)', (input) => {
        expect(DashboardStats.headline(input))
            .toEqual({ total: '-', topCategory: 'N/A', stars: '0' });
    });
});

describe('loadMoreLabel', () => {
    it('shows progress through the catalogue', () => {
        expect(DashboardStats.loadMoreLabel(24, { total: 37, has_more: true }))
            .toBe('Load more (24 of 37)');
    });

    it('returns null on the last page', () => {
        expect(DashboardStats.loadMoreLabel(37, { total: 37, has_more: false })).toBeNull();
    });

    it.each([null, undefined, {}])('returns null for %s metadata', (input) => {
        expect(DashboardStats.loadMoreLabel(0, input)).toBeNull();
    });
});

describe('completeMessage', () => {
    it('reports the final count', () => {
        expect(DashboardStats.completeMessage({ total: 37 })).toBe('Showing all 37 agents.');
    });

    it('says nothing when there are no agents at all', () => {
        expect(DashboardStats.completeMessage({ total: 0 })).toBeNull();
        expect(DashboardStats.completeMessage(null)).toBeNull();
    });
});

describe('pageQuery', () => {
    it('builds the paging query string', () => {
        expect(DashboardStats.pageQuery(0, 24)).toBe('?limit=24&offset=0');
        expect(DashboardStats.pageQuery(24, 24)).toBe('?limit=24&offset=24');
    });
});
