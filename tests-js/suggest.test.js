import { beforeAll, describe, expect, it } from 'vitest';

import { loadScript } from './helpers.js';

let S;
const ENTRIES = [
    { name: 'ComfyUI' }, { name: 'Cursor' }, { name: 'Vocode' },
    { name: 'Claude Code' }, { name: 'Cline' }, { name: 'Aider' },
];

beforeAll(() => { S = loadScript('suggest.js', 'Suggest'); });

describe('ranking', () => {
    it('returns nothing for an empty query', () => {
        expect(S.rank(ENTRIES, '')).toEqual([]);
        expect(S.rank(ENTRIES, '   ')).toEqual([]);
    });

    it('prefers a prefix match over a substring match', () => {
        const names = S.rank(ENTRIES, 'co').map(e => e.name);
        expect(names[0]).toBe('ComfyUI');
        expect(names).toContain('Vocode');
        expect(names.indexOf('ComfyUI')).toBeLessThan(names.indexOf('Vocode'));
    });

    it('is case-insensitive', () => {
        expect(S.rank(ENTRIES, 'CURSOR').map(e => e.name)).toEqual(['Cursor']);
    });

    it('sorts alphabetically within each group', () => {
        const names = S.rank(ENTRIES, 'c').map(e => e.name);
        expect(names).toEqual(['Claude Code', 'Cline', 'ComfyUI', 'Cursor', 'Vocode']);
    });

    it('matches across a space', () => {
        expect(S.rank(ENTRIES, 'claude c').map(e => e.name)).toEqual(['Claude Code']);
    });

    it('caps the number of results', () => {
        const many = Array.from({ length: 50 }, (_, i) => ({ name: `agent${i}` }));
        expect(S.rank(many, 'agent')).toHaveLength(S.MAX);
    });

    it('honours an explicit limit', () => {
        expect(S.rank(ENTRIES, 'c', 2)).toHaveLength(2);
    });

    it('returns nothing when nothing matches', () => {
        expect(S.rank(ENTRIES, 'zzzz')).toEqual([]);
    });

    it('tolerates entries with no name', () => {
        expect(() => S.rank([{}, { name: null }], 'a')).not.toThrow();
    });
});

describe('highlighting', () => {
    it('splits around the match', () => {
        expect(S.segments('ComfyUI', 'omf')).toEqual([
            { text: 'C', match: false },
            { text: 'omf', match: true },
            { text: 'yUI', match: false },
        ]);
    });

    it('handles a match at the start', () => {
        expect(S.segments('Cursor', 'cur')).toEqual([
            { text: 'Cur', match: true },
            { text: 'sor', match: false },
        ]);
    });

    it('handles a match at the end', () => {
        expect(S.segments('Aider', 'der')).toEqual([
            { text: 'Ai', match: false },
            { text: 'der', match: true },
        ]);
    });

    it('preserves the original casing', () => {
        expect(S.segments('ComfyUI', 'comfy')[0]).toEqual({ text: 'Comfy', match: true });
    });

    it('returns the whole name when there is no match', () => {
        expect(S.segments('Aider', 'zz')).toEqual([{ text: 'Aider', match: false }]);
    });
});

describe('keyboard movement', () => {
    it('starts at the first item going down', () => {
        expect(S.nextIndex(-1, 3, 1)).toBe(0);
    });

    it('starts at the last item going up', () => {
        expect(S.nextIndex(-1, 3, -1)).toBe(2);
    });

    it('wraps past the end', () => {
        expect(S.nextIndex(2, 3, 1)).toBe(0);
    });

    it('wraps before the start', () => {
        expect(S.nextIndex(0, 3, -1)).toBe(2);
    });

    it('stays put with no items', () => {
        expect(S.nextIndex(-1, 0, 1)).toBe(-1);
    });
});
