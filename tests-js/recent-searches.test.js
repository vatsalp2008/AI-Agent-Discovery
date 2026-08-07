import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { loadScript } from './helpers.js';

let Recent;

beforeEach(() => {
    localStorage.clear();
    Recent = loadScript('recent-searches.js', 'RecentSearches');
});

afterEach(() => localStorage.clear());

describe('recording searches', () => {
    it('starts empty', () => {
        expect(Recent.read()).toEqual([]);
    });

    it('keeps the most recent first', () => {
        Recent.add('first');
        Recent.add('second');
        expect(Recent.read().map(e => e.query)).toEqual(['second', 'first']);
    });

    it('moves a repeated query to the front instead of duplicating', () => {
        Recent.add('alpha');
        Recent.add('beta');
        Recent.add('alpha');
        expect(Recent.read().map(e => e.query)).toEqual(['alpha', 'beta']);
    });

    it('treats queries case-insensitively for deduplication', () => {
        Recent.add('Vector Search');
        Recent.add('vector search');
        expect(Recent.read()).toHaveLength(1);
    });

    it('remembers the category alongside the query', () => {
        Recent.add('editor', 'Code Generation');
        expect(Recent.read()[0].category).toBe('Code Generation');
    });

    it('trims whitespace and ignores blank queries', () => {
        Recent.add('  spaced  ');
        Recent.add('   ');
        expect(Recent.read().map(e => e.query)).toEqual(['spaced']);
    });

    it('caps the history', () => {
        for (let i = 0; i < Recent.LIMIT + 5; i += 1) Recent.add(`query ${i}`);
        expect(Recent.read()).toHaveLength(Recent.LIMIT);
    });
});

describe('resilience', () => {
    it('survives corrupt stored data', () => {
        localStorage.setItem(Recent.STORAGE_KEY, 'not json');
        expect(Recent.read()).toEqual([]);
    });

    it('survives a stored value that is not an array', () => {
        localStorage.setItem(Recent.STORAGE_KEY, '{"query":"x"}');
        expect(Recent.read()).toEqual([]);
    });

    it('drops malformed entries', () => {
        localStorage.setItem(Recent.STORAGE_KEY, JSON.stringify([{ query: 'ok' }, { nope: 1 }, null]));
        expect(Recent.read().map(e => e.query)).toEqual(['ok']);
    });

    it('does not throw when storage is unavailable', () => {
        const real = Storage.prototype.setItem;
        Storage.prototype.setItem = () => { throw new Error('denied'); };
        try {
            expect(() => Recent.add('x')).not.toThrow();
        } finally {
            Storage.prototype.setItem = real;
        }
    });
});

describe('presentation', () => {
    it('labels a plain query', () => {
        expect(Recent.label({ query: 'rag', category: null })).toBe('rag');
    });

    it('labels a filtered query with its category', () => {
        expect(Recent.label({ query: 'rag', category: 'Research' })).toBe('rag · Research');
    });

    it('clears the history', () => {
        Recent.add('x');
        Recent.clear();
        expect(Recent.read()).toEqual([]);
    });
});
