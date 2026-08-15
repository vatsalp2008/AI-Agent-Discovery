import { beforeEach, describe, expect, it } from 'vitest';

import SavedSearches from '../ai-agent-discovery/frontend/static/js/saved-searches.js';

/** Search results in the shape /api/search returns. */
function results(...agents) {
    return agents.map(([name, stars]) => ({
        name,
        metadata: { name, stars, category: 'Automation' },
    }));
}

beforeEach(() => localStorage.clear());

describe('saving', () => {
    it('keeps a search and its results', () => {
        SavedSearches.save('run a model locally', '', results(['Ollama', 100]));

        const [entry] = SavedSearches.list();
        expect(entry.query).toBe('run a model locally');
        expect(entry.snapshot.names).toEqual(['Ollama']);
        expect(entry.snapshot.stars.Ollama).toBe(100);
    });

    it('records when the snapshot was taken', () => {
        SavedSearches.save('q', '', results(['A', 1]));
        expect(Date.parse(SavedSearches.list()[0].snapshot.at)).not.toBeNaN();
    });

    it('saving the same search twice replaces it', () => {
        SavedSearches.save('same', '', results(['A', 1]));
        SavedSearches.save('same', '', results(['B', 2]));

        expect(SavedSearches.list()).toHaveLength(1);
        expect(SavedSearches.list()[0].snapshot.names).toEqual(['B']);
    });

    it('treats the same query under a different filter as a separate search', () => {
        SavedSearches.save('agents', '', results(['A', 1]));
        SavedSearches.save('agents', 'Robotics', results(['B', 1]));
        expect(SavedSearches.list()).toHaveLength(2);
    });

    it('matches a saved search regardless of case or padding', () => {
        SavedSearches.save('Run A Model', '', results(['A', 1]));
        expect(SavedSearches.has('  run a model  ', '')).toBe(true);
    });

    it('refuses a blank query', () => {
        expect(SavedSearches.save('   ', '', results(['A', 1]))).toBe(false);
        expect(SavedSearches.list()).toEqual([]);
    });

    it('newest first', () => {
        SavedSearches.save('first', '', results(['A', 1]));
        SavedSearches.save('second', '', results(['B', 1]));
        expect(SavedSearches.list().map(e => e.query)).toEqual(['second', 'first']);
    });

    it('drops the oldest past the cap rather than refusing the save', () => {
        for (let i = 0; i < SavedSearches.MAX_SAVED + 5; i += 1) {
            SavedSearches.save(`query ${i}`, '', results(['A', 1]));
        }
        const saved = SavedSearches.list();
        expect(saved).toHaveLength(SavedSearches.MAX_SAVED);
        expect(saved[0].query).toBe(`query ${SavedSearches.MAX_SAVED + 4}`);
    });
});

describe('removing', () => {
    it('removes one search', () => {
        SavedSearches.save('keep', '', results(['A', 1]));
        SavedSearches.save('drop', '', results(['B', 1]));

        expect(SavedSearches.remove('drop', '')).toBe(true);
        expect(SavedSearches.list().map(e => e.query)).toEqual(['keep']);
    });

    it('reports when there was nothing to remove', () => {
        expect(SavedSearches.remove('never saved', '')).toBe(false);
    });

    it('clears everything', () => {
        SavedSearches.save('a', '', results(['A', 1]));
        SavedSearches.clear();
        expect(SavedSearches.list()).toEqual([]);
    });
});

describe('diffing against a snapshot', () => {
    it('reports an agent that now matches and did not before', () => {
        const stored = SavedSearches.snapshot(results(['Ollama', 100]));
        const changes = SavedSearches.diff(stored, results(['Ollama', 100], ['MLX', 50]));

        expect(changes.added).toEqual(['MLX']);
        expect(changes.removed).toEqual([]);
    });

    it('reports an agent that dropped out', () => {
        const stored = SavedSearches.snapshot(results(['Ollama', 100], ['MLX', 50]));
        const changes = SavedSearches.diff(stored, results(['Ollama', 100]));

        expect(changes.removed).toEqual(['MLX']);
        expect(changes.added).toEqual([]);
    });

    it('reports meaningful star movement', () => {
        const stored = SavedSearches.snapshot(results(['Ollama', 100]));
        const changes = SavedSearches.diff(stored, results(['Ollama', 400]));

        expect(changes.moved).toEqual([{ name: 'Ollama', from: 100, to: 400 }]);
    });

    it('ignores star movement that is noise at that scale', () => {
        /** 40,000 to 40,300 is not news; 40 to 400 is. */
        const stored = SavedSearches.snapshot(results(['Big', 40000]));
        const changes = SavedSearches.diff(stored, results(['Big', 40300]));

        expect(changes.moved).toEqual([]);
    });

    it('reports a fall as well as a rise', () => {
        const stored = SavedSearches.snapshot(results(['Fading', 1000]));
        const changes = SavedSearches.diff(stored, results(['Fading', 500]));

        expect(changes.moved[0]).toMatchObject({ name: 'Fading', from: 1000, to: 500 });
    });

    it('says nothing changed when nothing did', () => {
        const stored = SavedSearches.snapshot(results(['Ollama', 100], ['MLX', 50]));
        const changes = SavedSearches.diff(stored, results(['Ollama', 100], ['MLX', 50]));

        expect(SavedSearches.isEmpty(changes)).toBe(true);
    });

    it('ranking changes on their own are not a change', () => {
        /** The set of answers is what matters, not their order — otherwise
         *  every check would report something and mean nothing. */
        const stored = SavedSearches.snapshot(results(['A', 1], ['B', 1]));
        const changes = SavedSearches.diff(stored, results(['B', 1], ['A', 1]));

        expect(SavedSearches.isEmpty(changes)).toBe(true);
    });

    it('an empty snapshot is not comparable', () => {
        /** Otherwise a search saved before snapshots existed would report
         *  every one of its results as brand new. */
        const changes = SavedSearches.diff({ names: [], stars: {} }, results(['A', 1]));
        expect(changes.comparable).toBe(false);
    });

    it('a snapshot with results is comparable', () => {
        const stored = SavedSearches.snapshot(results(['A', 1]));
        expect(SavedSearches.diff(stored, results(['A', 1])).comparable).toBe(true);
    });

    it('survives an agent that has no star count', () => {
        const stored = SavedSearches.snapshot([{ name: 'NoStars', metadata: { name: 'NoStars' } }]);
        const changes = SavedSearches.diff(stored, [{ name: 'NoStars', metadata: { name: 'NoStars' } }]);

        expect(SavedSearches.isEmpty(changes)).toBe(true);
    });

    it('does not divide by zero on an agent that had none', () => {
        const stored = SavedSearches.snapshot(results(['New', 0]));
        const changes = SavedSearches.diff(stored, results(['New', 50]));

        expect(changes.moved).toEqual([]);
    });
});

describe('refreshing a snapshot', () => {
    it('replaces the stored results so the next check starts from here', () => {
        SavedSearches.save('q', '', results(['A', 1]));
        SavedSearches.refresh('q', '', results(['A', 1], ['B', 2]));

        const changes = SavedSearches.diff(
            SavedSearches.list()[0].snapshot, results(['A', 1], ['B', 2]));
        expect(SavedSearches.isEmpty(changes)).toBe(true);
    });

    it('reports when there is nothing to refresh', () => {
        expect(SavedSearches.refresh('never saved', '', results(['A', 1]))).toBe(false);
    });
});

describe('reading damaged storage', () => {
    it('survives text that is not JSON', () => {
        localStorage.setItem('agentdiscovery:saved-searches', 'not json');
        expect(SavedSearches.list()).toEqual([]);
    });

    it('survives an object where a list belongs', () => {
        localStorage.setItem('agentdiscovery:saved-searches', '{"query":"x"}');
        expect(SavedSearches.list()).toEqual([]);
    });

    it('drops entries with no query', () => {
        localStorage.setItem('agentdiscovery:saved-searches',
            JSON.stringify([{ query: 'good' }, { query: '' }, { nope: 1 }, null]));
        expect(SavedSearches.list().map(e => e.query)).toEqual(['good']);
    });

    it('drops duplicates left by a hand edit', () => {
        localStorage.setItem('agentdiscovery:saved-searches',
            JSON.stringify([{ query: 'same' }, { query: 'Same' }]));
        expect(SavedSearches.list()).toHaveLength(1);
    });

    it('tolerates a snapshot written by an older version', () => {
        localStorage.setItem('agentdiscovery:saved-searches',
            JSON.stringify([{ query: 'q', snapshot: { names: 'not a list', stars: 7 } }]));

        const [entry] = SavedSearches.list();
        expect(entry.snapshot.names).toEqual([]);
        expect(entry.snapshot.stars).toEqual({});
    });

    it('ignores a star count that is not a number', () => {
        localStorage.setItem('agentdiscovery:saved-searches',
            JSON.stringify([{ query: 'q', snapshot: { names: ['A'], stars: { A: 'lots' } } }]));
        expect(SavedSearches.list()[0].snapshot.stars).toEqual({});
    });
});

describe('exporting', () => {
    it('writes a labelled payload', () => {
        SavedSearches.save('run a model', '', results(['Ollama', 100]));
        const payload = JSON.parse(SavedSearches.exportAll());

        expect(payload.kind).toBe('agentdiscovery-saved-searches');
        expect(payload.version).toBe(1);
        expect(payload.searches).toHaveLength(1);
    });

    it('carries the snapshot, so an import keeps its baseline', () => {
        SavedSearches.save('q', '', results(['A', 5]));
        const [entry] = JSON.parse(SavedSearches.exportAll()).searches;

        expect(entry.snapshot.names).toEqual(['A']);
        expect(entry.snapshot.stars.A).toBe(5);
    });

    it('exports an empty list rather than failing', () => {
        expect(JSON.parse(SavedSearches.exportAll()).searches).toEqual([]);
    });
});

describe('importing', () => {
    function payload(...entries) {
        return JSON.stringify({
            kind: 'agentdiscovery-saved-searches',
            version: 1,
            searches: entries,
        });
    }

    it('adds searches that are not already there', () => {
        const result = SavedSearches.importAll(payload(
            { query: 'imported', category: '', snapshot: { names: ['A'], stars: { A: 1 } } }));

        expect(result).toMatchObject({ ok: true, added: 1, skipped: 0 });
        expect(SavedSearches.list().map(e => e.query)).toEqual(['imported']);
    });

    it('merges rather than replacing', () => {
        SavedSearches.save('mine', '', results(['A', 1]));
        SavedSearches.importAll(payload({ query: 'theirs', category: '' }));

        expect(SavedSearches.list().map(e => e.query).sort()).toEqual(['mine', 'theirs']);
    });

    it('keeps the local snapshot on a clash', () => {
        /** The local one is the more recent baseline. Adopting an older
         *  snapshot would make the next check re-report changes already seen. */
        SavedSearches.save('same', '', results(['Current', 10]));
        SavedSearches.importAll(payload(
            { query: 'same', category: '', snapshot: { names: ['Stale'], stars: { Stale: 1 } } }));

        expect(SavedSearches.list()[0].snapshot.names).toEqual(['Current']);
    });

    it('counts what it skipped', () => {
        SavedSearches.save('same', '', results(['A', 1]));
        const result = SavedSearches.importAll(payload(
            { query: 'same', category: '' }, { query: 'new', category: '' }));

        expect(result).toMatchObject({ added: 1, skipped: 1 });
    });

    it('treats the same query under a different filter as new', () => {
        SavedSearches.save('agents', '', results(['A', 1]));
        const result = SavedSearches.importAll(payload({ query: 'agents', category: 'Robotics' }));

        expect(result.added).toBe(1);
        expect(SavedSearches.list()).toHaveLength(2);
    });

    it('stops at the cap instead of overflowing it', () => {
        for (let i = 0; i < SavedSearches.MAX_SAVED; i += 1) {
            SavedSearches.save(`local ${i}`, '', results(['A', 1]));
        }
        const result = SavedSearches.importAll(payload({ query: 'one too many', category: '' }));

        expect(result).toMatchObject({ added: 0, full: 1 });
        expect(SavedSearches.list()).toHaveLength(SavedSearches.MAX_SAVED);
    });

    it('counts "no room" apart from "already saved"', () => {
        /** Both used to increment `skipped`, so a full backup imported into
         *  a full list reported "nothing new" while discarding everything. */
        SavedSearches.save('mine', '', results(['A', 1]));
        for (let i = 1; i < SavedSearches.MAX_SAVED; i += 1) {
            SavedSearches.save(`filler ${i}`, '', results(['A', 1]));
        }
        const result = SavedSearches.importAll(payload(
            { query: 'mine', category: '' }, { query: 'no room for this', category: '' }));

        expect(result).toMatchObject({ added: 0, skipped: 1, full: 1 });
    });

    it('survives a category that is not a string', () => {
        /** Threw out of keyFor, out of importAll, and out of the FileReader
         *  handler — so the page showed no message and imported nothing. */
        const result = SavedSearches.importAll(payload(
            { query: 'numeric', category: 123 },
            { query: 'listy', category: ['a'] },
            { query: 'objecty', category: { a: 1 } }));

        expect(result.ok).toBe(true);
        expect(SavedSearches.list().every(e => typeof e.category === 'string')).toBe(true);
    });

    it('treats a non-string category as no filter', () => {
        SavedSearches.importAll(payload({ query: 'q', category: 42 }));
        expect(SavedSearches.list()[0].category).toBe('');
    });

    it('rejects text that is not JSON', () => {
        expect(SavedSearches.importAll('nonsense')).toMatchObject({ ok: false });
        expect(SavedSearches.importAll('nonsense').reason).toContain('valid JSON');
    });

    it('rejects a collections export, which is a different shape', () => {
        const collections = JSON.stringify({ kind: 'agentdiscovery-collections', collections: {} });
        expect(SavedSearches.importAll(collections).reason).toContain('not a saved-searches export');
    });

    it('rejects a payload with no searches array', () => {
        const bad = JSON.stringify({ kind: 'agentdiscovery-saved-searches', searches: 'nope' });
        expect(SavedSearches.importAll(bad).reason).toContain('no saved searches');
    });

    it('ignores entries with no query', () => {
        const result = SavedSearches.importAll(payload(
            { query: 'good' }, { query: '' }, { nope: 1 }, null));
        expect(result.added).toBe(1);
    });

    it('round-trips its own export', () => {
        SavedSearches.save('one', '', results(['A', 1]));
        SavedSearches.save('two', 'Robotics', results(['B', 2]));
        const exported = SavedSearches.exportAll();

        SavedSearches.clear();
        expect(SavedSearches.importAll(exported)).toMatchObject({ ok: true, added: 2 });
        expect(SavedSearches.list().map(e => e.query).sort()).toEqual(['one', 'two']);
    });
});
