import { beforeAll, describe, expect, it } from 'vitest';

import { loadScript } from './helpers.js';

let SearchState;

beforeAll(() => {
    SearchState = loadScript('search-state.js', 'SearchState');
});

describe('fromSearch', () => {
    it('reads the query and category', () => {
        expect(SearchState.fromSearch('?q=code+editor&category=Code%20Generation'))
            .toEqual({ query: 'code editor', category: 'Code Generation' });
    });

    it.each(['', '?', undefined, null])('returns empty state for %s', (input) => {
        expect(SearchState.fromSearch(input)).toEqual({ query: '', category: null });
    });

    it('treats a blank category as absent', () => {
        expect(SearchState.fromSearch('?q=x&category=').category).toBeNull();
        expect(SearchState.fromSearch('?q=x&category=%20%20').category).toBeNull();
    });

    it('trims surrounding whitespace', () => {
        expect(SearchState.fromSearch('?q=%20%20spaced%20%20').query).toBe('spaced');
    });

    it('ignores unrelated parameters', () => {
        expect(SearchState.fromSearch('?utm_source=x&q=real')).toEqual({
            query: 'real', category: null,
        });
    });
});

describe('toUrl', () => {
    it('encodes query and category', () => {
        expect(SearchState.toUrl('/', { query: 'vector db', category: 'Research' }))
            .toBe('/?q=vector+db&category=Research');
    });

    it('returns a bare path when there is nothing to encode', () => {
        expect(SearchState.toUrl('/', {})).toBe('/');
        expect(SearchState.toUrl('/', { query: '', category: null })).toBe('/');
    });

    it('keeps a category with no query', () => {
        expect(SearchState.toUrl('/', { category: 'Research' })).toBe('/?category=Research');
    });

    it('round-trips through fromSearch', () => {
        const state = { query: 'a & b', category: 'Code Generation' };
        const url = SearchState.toUrl('/', state);
        expect(SearchState.fromSearch(url.slice(url.indexOf('?')))).toEqual(state);
    });

    it('preserves a non-root pathname', () => {
        expect(SearchState.toUrl('/search', { query: 'x' })).toBe('/search?q=x');
    });
});

describe('searchBody', () => {
    it('sends only the query by default', () => {
        expect(SearchState.searchBody({ query: 'x' })).toEqual({ query: 'x' });
    });

    it('omits absent optional fields rather than sending null', () => {
        // The API rejects a non-string category and a non-boolean summarize.
        expect(SearchState.searchBody({ query: 'x', category: null, summarize: false }))
            .toEqual({ query: 'x' });
    });

    it('includes the category when set', () => {
        expect(SearchState.searchBody({ query: 'x', category: 'Research' }))
            .toEqual({ query: 'x', category: 'Research' });
    });

    it('sends summarize as a real boolean', () => {
        const body = SearchState.searchBody({ query: 'x', summarize: true });
        expect(body.summarize).toBe(true);
    });
});

describe('emptyMessage', () => {
    it('mentions the active category', () => {
        expect(SearchState.emptyMessage('Research')).toContain('Research');
    });

    it('falls back to a generic message', () => {
        expect(SearchState.emptyMessage(null)).toBe('No agents found matching your query.');
    });
});
