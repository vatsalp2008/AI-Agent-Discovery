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
