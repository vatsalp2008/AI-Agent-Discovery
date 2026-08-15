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
        /** Read from the module rather than hardcoded: a link the API
         *  refuses on arrival is worse than one that takes the first few. */
        C.create('Big');
        for (let i = 0; i < C.maxCompare() + 3; i += 1) C.add('Big', `agent${i}`);

        expect(decodeURIComponent(C.compareUrl('Big')).split(','))
            .toHaveLength(C.maxCompare());
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

describe('export and import', () => {
    it('exports a labelled payload', () => {
        C.create('Coding');
        C.add('Coding', 'Aider');
        const payload = JSON.parse(C.exportAll());
        expect(payload.kind).toBe('agentdiscovery-collections');
        expect(payload.collections.Coding).toEqual(['Aider']);
        expect(Number.isNaN(Date.parse(payload.exported_at))).toBe(false);
    });

    it('round-trips through a fresh browser', () => {
        C.create('Coding');
        C.add('Coding', 'Aider');
        const backup = C.exportAll();

        localStorage.clear();
        expect(C.importAll(backup)).toEqual({ ok: true, added: 1, merged: 0 });
        expect(C.agentsIn('Coding')).toEqual(['Aider']);
    });

    it('merges rather than replacing', () => {
        C.create('Coding');
        C.add('Coding', 'Aider');
        const backup = C.exportAll();

        localStorage.clear();
        C.create('Coding');
        C.add('Coding', 'Cursor');
        C.create('Research');

        const result = C.importAll(backup);
        expect(result.merged).toBe(1);
        expect(C.agentsIn('Coding').sort()).toEqual(['Aider', 'Cursor']);
        expect(C.names()).toContain('Research');   // untouched
    });

    it('does not duplicate an agent already present', () => {
        C.create('Coding');
        C.add('Coding', 'Aider');
        const backup = C.exportAll();
        C.importAll(backup);
        expect(C.agentsIn('Coding')).toEqual(['Aider']);
    });

    it('rejects invalid JSON', () => {
        expect(C.importAll('{ not json').reason).toContain('valid JSON');
    });

    it('rejects a file that is not a collections export', () => {
        expect(C.importAll(JSON.stringify({ kind: 'something-else' })).reason)
            .toContain('not a collections export');
    });

    it('rejects an array', () => {
        expect(C.importAll('[1,2,3]').ok).toBe(false);
    });

    it('rejects a payload with no collections', () => {
        expect(C.importAll(JSON.stringify({ kind: 'agentdiscovery-collections' })).reason)
            .toContain('no collections');
    });

    it('skips malformed entries inside a valid payload', () => {
        const result = C.importAll(JSON.stringify({
            kind: 'agentdiscovery-collections',
            collections: { Good: ['Aider'], Bad: 'not an array', '  ': ['x'] },
        }));
        expect(result.ok).toBe(true);
        expect(C.names()).toEqual(['Good']);
    });

    it('respects the collection cap on import', () => {
        const many = {};
        for (let i = 0; i < C.MAX_COLLECTIONS + 5; i += 1) many[`c${i}`] = [];
        C.importAll(JSON.stringify({ kind: 'agentdiscovery-collections', collections: many }));
        expect(C.names().length).toBeLessThanOrEqual(C.MAX_COLLECTIONS);
    });

    it('respects the per-collection cap on import', () => {
        const agents = Array.from({ length: C.MAX_AGENTS + 10 }, (_, i) => `agent${i}`);
        C.importAll(JSON.stringify({
            kind: 'agentdiscovery-collections', collections: { Big: agents },
        }));
        expect(C.agentsIn('Big').length).toBe(C.MAX_AGENTS);
    });
});

describe('names that collide with Object prototype members', () => {
    // `name in object` walks the prototype chain, so these used to report
    // "already exists" and then blow up when read back as arrays.
    const dangerous = ['constructor', 'toString', 'hasOwnProperty', 'valueOf', '__proto__'];

    it.each(dangerous)('can create a collection called %s', (name) => {
        expect(C.create(name).ok).toBe(true);
        expect(C.names()).toContain(name);
    });

    it.each(dangerous)('can add an agent to %s', (name) => {
        C.create(name);
        expect(C.add(name, 'Aider').ok).toBe(true);
        expect(C.agentsIn(name)).toEqual(['Aider']);
    });

    it('reports a genuine duplicate of such a name', () => {
        C.create('constructor');
        expect(C.create('constructor').reason).toContain('already exists');
    });

    it('adding to a non-existent prototype-ish name is refused', () => {
        expect(C.add('toString', 'Aider').reason).toContain('No such collection');
    });

    it('imports a payload containing such a key without throwing', () => {
        const payload = JSON.stringify({
            kind: 'agentdiscovery-collections',
            collections: { constructor: ['Aider'], Normal: ['Cursor'] },
        });
        expect(() => C.importAll(payload)).not.toThrow();
        expect(C.agentsIn('constructor')).toEqual(['Aider']);
        expect(C.agentsIn('Normal')).toEqual(['Cursor']);
    });

    it('round-trips such a collection through export and import', () => {
        C.create('toString');
        C.add('toString', 'Aider');
        const backup = C.exportAll();

        localStorage.clear();
        expect(C.importAll(backup).ok).toBe(true);
        expect(C.agentsIn('toString')).toEqual(['Aider']);
    });
});

describe('exporting one collection', () => {
    it('carries only that collection', () => {
        Collections.create('Keep');
        Collections.create('Other');
        Collections.add('Keep', 'Aider');
        Collections.add('Other', 'Cursor');

        const payload = JSON.parse(Collections.exportOne('Keep'));
        expect(Object.keys(payload.collections)).toEqual(['Keep']);
        expect(payload.collections.Keep).toEqual(['Aider']);
    });

    it('uses the same kind, so it imports back', () => {
        /** Sharing one shortlist should merge on the other side rather than
         *  being refused as a different format. */
        Collections.create('Shared');
        Collections.add('Shared', 'Aider');
        const payload = Collections.exportOne('Shared');

        Collections.clear();
        expect(Collections.importAll(payload)).toMatchObject({ ok: true, added: 1 });
        expect(Collections.agentsIn('Shared')).toEqual(['Aider']);
    });

    it('returns null for a collection that is not there', () => {
        expect(Collections.exportOne('Missing')).toBeNull();
    });

    it('exports an empty collection as an empty list', () => {
        Collections.create('Empty');
        expect(JSON.parse(Collections.exportOne('Empty')).collections.Empty).toEqual([]);
    });
});
