import { beforeEach, afterEach, describe, expect, it } from 'vitest';

import { loadScript } from './helpers.js';

let C;

beforeEach(() => {
    localStorage.clear();
    C = loadScript('collections.js', 'Collections');
});

afterEach(() => localStorage.clear());

describe('creating', () => {
    it('starts with none', () => {
        expect(C.names()).toEqual([]);
    });

    it('creates a collection', () => {
        expect(C.create('Coding').ok).toBe(true);
        expect(C.names()).toEqual(['Coding']);
    });

    it('trims the name', () => {
        C.create('  Spaced  ');
        expect(C.names()).toEqual(['Spaced']);
    });

    it('rejects a blank name', () => {
        expect(C.create('   ').ok).toBe(false);
        expect(C.create('').reason).toContain('needs a name');
    });

    it('rejects a duplicate', () => {
        C.create('Coding');
        expect(C.create('Coding').reason).toContain('already exists');
    });

    it('caps the number of collections', () => {
        for (let i = 0; i < C.MAX_COLLECTIONS; i += 1) C.create(`c${i}`);
        const result = C.create('one too many');
        expect(result.ok).toBe(false);
        expect(result.reason).toContain('at most');
    });

    it('sorts names', () => {
        C.create('Zebra');
        C.create('Alpha');
        expect(C.names()).toEqual(['Alpha', 'Zebra']);
    });
});

describe('membership', () => {
    beforeEach(() => C.create('Coding'));

    it('adds an agent', () => {
        expect(C.add('Coding', 'Aider').ok).toBe(true);
        expect(C.agentsIn('Coding')).toEqual(['Aider']);
    });

    it('refuses a duplicate agent', () => {
        C.add('Coding', 'Aider');
        const result = C.add('Coding', 'aider');
        expect(result.ok).toBe(false);
        expect(result.reason).toContain('already in');
    });

    it('refuses an unknown collection', () => {
        expect(C.add('Nope', 'Aider').reason).toContain('No such collection');
    });

    it('caps agents per collection', () => {
        for (let i = 0; i < C.MAX_AGENTS; i += 1) C.add('Coding', `agent${i}`);
        expect(C.add('Coding', 'overflow').reason).toContain('full');
    });

    it('removes an agent, case-insensitively', () => {
        C.add('Coding', 'Aider');
        C.remove('Coding', 'AIDER');
        expect(C.agentsIn('Coding')).toEqual([]);
    });

    it('removing something absent is harmless', () => {
        expect(C.remove('Coding', 'Ghost').ok).toBe(true);
    });

    it('reports which collections hold an agent', () => {
        C.create('Research');
        C.add('Coding', 'Aider');
        C.add('Research', 'Aider');
        expect(C.containing('aider')).toEqual(['Coding', 'Research']);
        expect(C.containing('Nobody')).toEqual([]);
    });

    it('deletes a collection', () => {
        C.destroy('Coding');
        expect(C.names()).toEqual([]);
    });
});

describe('comparing', () => {
    it('builds a compare URL', () => {
        C.create('Coding');
        C.add('Coding', 'Aider');
        C.add('Coding', 'Cursor');
        expect(decodeURIComponent(C.compareUrl('Coding'))).toBe('/compare?names=Aider,Cursor');
    });

    it('needs at least two agents', () => {
        C.create('Coding');
        C.add('Coding', 'Aider');
        expect(C.compareUrl('Coding')).toBeNull();
    });

    it('caps at what the compare API accepts', () => {
        C.create('Big');
        ['a', 'b', 'c', 'd', 'e', 'f'].forEach(n => C.add('Big', n));
        expect(decodeURIComponent(C.compareUrl('Big')).split(',')).toHaveLength(4);
    });
});

describe('resilience', () => {
    it('survives corrupt storage', () => {
        localStorage.setItem(C.STORAGE_KEY, 'not json');
        expect(C.read()).toEqual({});
    });

    it('survives an array where an object belongs', () => {
        localStorage.setItem(C.STORAGE_KEY, '["nope"]');
        expect(C.read()).toEqual({});
    });

    it('drops malformed entries', () => {
        localStorage.setItem(C.STORAGE_KEY, JSON.stringify({ ok: ['Aider'], bad: 'not an array' }));
        expect(Object.keys(C.read())).toEqual(['ok']);
    });

    it('reports a failure when storage is unavailable', () => {
        const real = Storage.prototype.setItem;
        Storage.prototype.setItem = () => { throw new Error('denied'); };
        try {
            const result = C.create('Coding');
            expect(result.ok).toBe(false);
            expect(result.reason).toContain('storage');
        } finally {
            Storage.prototype.setItem = real;
        }
    });
});
