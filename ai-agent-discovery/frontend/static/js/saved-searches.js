/**
 * Searches you want to keep an eye on, kept in localStorage.
 *
 * A catalogue that grows is a catalogue whose answers change. Someone who
 * searched "run a model on apple silicon" six months ago got three results;
 * there are more now, and nothing told them.
 *
 * Saving a search stores a snapshot of what it returned — which agents, and
 * how many stars each had. Re-running it later and diffing against that
 * snapshot is the whole feature: new matches, ones that dropped out, and
 * projects whose momentum changed.
 *
 * Client-side on purpose, for the same reason as collections: the premise of
 * the project is that what you look for never leaves your machine. A list of
 * the questions someone keeps asking is about as revealing as data gets.
 */
const SavedSearches = (() => {
    const STORAGE_KEY = 'agentdiscovery:saved-searches';
    const MAX_SAVED = 20;

    /** Stars must move by at least this fraction to be worth reporting. */
    const STAR_CHANGE = 0.05;

    /**
     * The identity of a search. Two saves of the same query and filter are
     * one saved search, not two — otherwise the list fills with duplicates
     * that all report the same thing.
     */
    function keyFor(query, category, maintained) {
        // Coerced rather than assumed to be strings: importAll() builds keys
        // from a hand-edited file, and a numeric category used to throw out
        // of here, out of the import, and out of the FileReader handler —
        // leaving no message and nothing imported.
        //
        // Separated by a newline, which cannot appear in either field: with
        // the two simply concatenated, ("ab", "") and ("a", "b") would be
        // the same saved search.
        const text = value => (typeof value === 'string' ? value : '').trim().toLowerCase();
        // The health filter is part of the identity, like the category: the
        // snapshot was taken with it applied, so re-running without it
        // reports every excluded project as brand new.
        return `${text(query)}\n${text(category)}\n${maintained ? '1' : ''}`;
    }

    function isRecord(entry) {
        return entry && typeof entry === 'object' && !Array.isArray(entry)
            && typeof entry.query === 'string' && entry.query.trim();
    }

    /** Normalise a stored snapshot, tolerating anything an older version wrote. */
    function cleanSnapshot(raw) {
        const names = Array.isArray(raw?.names)
            ? raw.names.filter(n => typeof n === 'string' && n.trim())
            : [];

        const stars = Object.create(null);
        if (raw?.stars && typeof raw.stars === 'object') {
            Object.entries(raw.stars).forEach(([name, count]) => {
                if (typeof name === 'string' && Number.isFinite(count)) stars[name] = count;
            });
        }
        return { names, stars, at: typeof raw?.at === 'string' ? raw.at : null };
    }

    function read() {
        try {
            const raw = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
            if (!Array.isArray(raw)) return [];

            const seen = new Set();
            const clean = [];
            raw.filter(isRecord).forEach(entry => {
                const key = keyFor(entry.query, entry.category, entry.maintained);
                if (seen.has(key)) return;   // a duplicate from a hand edit
                seen.add(key);
                clean.push({
                    query: entry.query.trim(),
                    category: typeof entry.category === 'string' ? entry.category.trim() : '',
                    maintained: Boolean(entry.maintained),
                    snapshot: cleanSnapshot(entry.snapshot),
                });
            });
            return clean.slice(0, MAX_SAVED);
        } catch (error) {
            return [];
        }
    }

    function write(entries) {
        try {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(entries.slice(0, MAX_SAVED)));
            return true;
        } catch (error) {
            return false;   // storage full or disabled
        }
    }

    /**
     * Turn search results into a snapshot.
     *
     * Only the name and the star count are kept. Storing the descriptions
     * would multiply the size for no gain — the diff is about which agents
     * answer the question, not how they describe themselves.
     */
    function snapshot(results) {
        const names = [];
        const stars = Object.create(null);

        (results || []).forEach(result => {
            const name = result?.metadata?.name ?? result?.name;
            if (typeof name !== 'string' || !name.trim()) return;
            names.push(name);
            const count = result?.metadata?.stars ?? result?.github_stars;
            if (Number.isFinite(count)) stars[name] = count;
        });

        return { names, stars, at: new Date().toISOString() };
    }

    /** Save a search, replacing any earlier save of the same query. */
    function save(query, category, results, { maintained = false } = {}) {
        if (typeof query !== 'string' || !query.trim()) return false;

        const key = keyFor(query, category, maintained);
        const entries = read().filter(
            e => keyFor(e.query, e.category, e.maintained) !== key);

        // Newest first, and the cap drops the oldest rather than refusing
        // the save — being told "you have too many saved searches" is not
        // something anyone wants to act on mid-search.
        entries.unshift({
            query: query.trim(),
            category: (category || '').trim(),
            maintained: Boolean(maintained),
            snapshot: snapshot(results),
        });
        return write(entries);
    }

    function remove(query, category, { maintained = false } = {}) {
        const key = keyFor(query, category, maintained);
        const entries = read();
        const kept = entries.filter(
            e => keyFor(e.query, e.category, e.maintained) !== key);
        if (kept.length === entries.length) return false;
        return write(kept);
    }

    function clear() {
        return write([]);
    }

    function list() {
        return read();
    }

    function has(query, category, { maintained = false } = {}) {
        const key = keyFor(query, category, maintained);
        return read().some(e => keyFor(e.query, e.category, e.maintained) === key);
    }

    /**
     * What changed between a stored snapshot and fresh results.
     *
     * Star movement is reported as a fraction rather than an absolute, so a
     * project going 40 to 400 registers and one going 40,000 to 40,300 does
     * not — the second is noise at that scale.
     */
    function diff(stored, results) {
        const before = cleanSnapshot(stored);
        const after = snapshot(results);

        const wasThere = new Set(before.names);
        const isThere = new Set(after.names);

        const moved = [];
        after.names.forEach(name => {
            const from = before.stars[name];
            const to = after.stars[name];
            if (!Number.isFinite(from) || !Number.isFinite(to) || from <= 0) return;
            if (Math.abs(to - from) / from >= STAR_CHANGE) moved.push({ name, from, to });
        });

        return {
            added: after.names.filter(n => !wasThere.has(n)),
            removed: before.names.filter(n => !isThere.has(n)),
            moved,
            // A search saved before any snapshot existed has nothing to
            // compare against; reporting every result as "new" would be
            // wrong, so callers check this first.
            comparable: before.names.length > 0,
        };
    }

    function isEmpty(changes) {
        return !changes.added.length && !changes.removed.length && !changes.moved.length;
    }

    /** Replace a saved search's snapshot, so the next check diffs from here. */
    function refresh(query, category, results, { maintained = false } = {}) {
        const key = keyFor(query, category, maintained);
        const entries = read();
        const entry = entries.find(
            e => keyFor(e.query, e.category, e.maintained) === key);
        if (!entry) return false;

        entry.snapshot = snapshot(results);
        return write(entries);
    }

    /** Serialise every saved search for backup or moving to another browser. */
    function exportAll() {
        return JSON.stringify({
            kind: 'agentdiscovery-saved-searches',
            version: 1,
            exported_at: new Date().toISOString(),
            searches: read(),
        }, null, 2);
    }

    /**
     * Merge an exported payload into what is already saved.
     *
     * Merges rather than replaces, like collections: importing a backup
     * should not destroy searches made since. On a clash the *local* entry
     * wins, because its snapshot is the more recent baseline — adopting an
     * older one would make the next check re-report changes that have
     * already been seen.
     */
    function importAll(text) {
        let payload;
        try {
            payload = JSON.parse(text);
        } catch (error) {
            return { ok: false, reason: 'That is not valid JSON.' };
        }

        if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
            return { ok: false, reason: 'Unrecognised file.' };
        }
        if (payload.kind !== 'agentdiscovery-saved-searches') {
            return { ok: false, reason: 'That file is not a saved-searches export.' };
        }
        if (!Array.isArray(payload.searches)) {
            return { ok: false, reason: 'The file has no saved searches in it.' };
        }

        const current = read();
        const seen = new Set(current.map(e => keyFor(e.query, e.category, e.maintained)));

        let added = 0;
        let skipped = 0;   // already saved here
        let full = 0;      // no room left
        payload.searches.filter(isRecord).forEach(entry => {
            const key = keyFor(entry.query, entry.category, entry.maintained);
            if (seen.has(key)) { skipped += 1; return; }
            // Counted apart from `skipped`: "you already have these" and
            // "these were thrown away because you are at the limit" are
            // opposite outcomes, and the second must not read as the first.
            if (current.length >= MAX_SAVED) { full += 1; return; }

            seen.add(key);
            current.push({
                query: entry.query.trim(),
                category: typeof entry.category === 'string' ? entry.category.trim() : '',
                maintained: Boolean(entry.maintained),
                snapshot: cleanSnapshot(entry.snapshot),
            });
            added += 1;
        });

        if (!write(current)) {
            return { ok: false, reason: 'Could not save; storage is unavailable.' };
        }
        return { ok: true, added, skipped, full };
    }

    return {
        save, remove, clear, list, has, diff, snapshot, refresh, isEmpty,
        exportAll, importAll, MAX_SAVED, STAR_CHANGE,
    };
})();

if (typeof module !== 'undefined') module.exports = SavedSearches;
