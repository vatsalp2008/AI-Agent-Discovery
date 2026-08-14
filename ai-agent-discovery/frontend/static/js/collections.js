/**
 * Named sets of agents, kept in localStorage.
 *
 * Client-side on purpose: the project's premise is that what you look for
 * never leaves your machine, and a shortlist of agents is exactly that kind
 * of signal. It also means collections need no accounts or server state.
 */
const Collections = (() => {
    const STORAGE_KEY = 'agentdiscovery:collections';
    const MAX_COLLECTIONS = 20;
    const MAX_AGENTS = 50;

    /**
     * Own-property check. Plain `name in object` walks the prototype chain, so
     * a collection called "constructor" or "toString" would look like it
     * already exists — and reading it back yields a function, not an array.
     */
    function has(object, name) {
        return Object.prototype.hasOwnProperty.call(object, name);
    }

    function read() {
        try {
            const raw = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
            if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return {};

            // Tolerate anything hand-edited or written by an older version.
            // Null prototype: nothing inherited can be mistaken for an entry.
            const clean = Object.create(null);
            Object.entries(raw).forEach(([name, agents]) => {
                if (typeof name === 'string' && name.trim() && Array.isArray(agents)) {
                    clean[name] = agents.filter(a => typeof a === 'string' && a.trim());
                }
            });
            return clean;
        } catch (error) {
            return {};
        }
    }

    function write(collections) {
        try {
            // Stringify the null-prototype object directly. Copying it onto a
            // plain {} first would lose a key called "__proto__", since that
            // assignment invokes the prototype setter instead of adding a key.
            localStorage.setItem(STORAGE_KEY, JSON.stringify(collections));
            return true;
        } catch (error) {
            return false;   // storage full or disabled
        }
    }

    function names() {
        return Object.keys(read()).sort((a, b) => a.localeCompare(b));
    }

    function agentsIn(name) {
        return read()[name] || [];
    }

    function create(name) {
        const trimmed = (name || '').trim();
        if (!trimmed) return { ok: false, reason: 'A collection needs a name.' };

        const collections = read();
        if (Object.keys(collections).length >= MAX_COLLECTIONS && !has(collections, trimmed)) {
            return { ok: false, reason: `You can keep at most ${MAX_COLLECTIONS} collections.` };
        }
        if (has(collections, trimmed)) return { ok: false, reason: 'That collection already exists.' };

        collections[trimmed] = [];
        return write(collections)
            ? { ok: true, name: trimmed }
            : { ok: false, reason: 'Could not save; browser storage is unavailable.' };
    }

    function add(name, agent) {
        const collections = read();
        if (!has(collections, name)) return { ok: false, reason: 'No such collection.' };

        const list = collections[name];
        if (list.some(a => a.toLowerCase() === agent.toLowerCase())) {
            return { ok: false, reason: `${agent} is already in ${name}.` };
        }
        if (list.length >= MAX_AGENTS) {
            return { ok: false, reason: `${name} is full (${MAX_AGENTS} agents).` };
        }

        list.push(agent);
        return write(collections) ? { ok: true } : { ok: false, reason: 'Could not save.' };
    }

    function remove(name, agent) {
        const collections = read();
        if (!has(collections, name)) return { ok: false, reason: 'No such collection.' };

        collections[name] = collections[name].filter(a => a.toLowerCase() !== agent.toLowerCase());
        return write(collections) ? { ok: true } : { ok: false, reason: 'Could not save.' };
    }

    function destroy(name) {
        const collections = read();
        delete collections[name];
        return write(collections) ? { ok: true } : { ok: false, reason: 'Could not save.' };
    }

    /** Which collections contain `agent`. */
    function containing(agent) {
        const needle = (agent || '').toLowerCase();
        return Object.entries(read())
            .filter(([, agents]) => agents.some(a => a.toLowerCase() === needle))
            .map(([name]) => name)
            .sort();
    }

    /** A /compare URL for a collection, capped at what the API accepts. */
    function compareUrl(name, max = 4) {
        const agents = agentsIn(name).slice(0, max);
        if (agents.length < 2) return null;
        return `/compare?names=${encodeURIComponent(agents.join(','))}`;
    }

    /** Serialise every collection for backup or moving to another browser. */
    function exportAll() {
        return JSON.stringify({
            kind: 'agentdiscovery-collections',
            version: 1,
            exported_at: new Date().toISOString(),
            collections: read(),
        }, null, 2);
    }

    /**
     * Serialise one collection, in the same shape as a full export.
     *
     * Same `kind` deliberately: importing it merges the one collection back
     * rather than being refused as a different format, which is what makes
     * sharing a single shortlist useful.
     */
    function exportOne(name) {
        const collections = read();
        if (!has(collections, name)) return null;

        return JSON.stringify({
            kind: 'agentdiscovery-collections',
            version: 1,
            exported_at: new Date().toISOString(),
            collections: { [name]: collections[name] },
        }, null, 2);
    }

    /**
     * Merge an exported payload into the existing collections.
     *
     * Merges rather than replaces: importing a backup should not silently
     * destroy collections made since. A name clash unions the two sets.
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
        if (payload.kind !== 'agentdiscovery-collections') {
            return { ok: false, reason: 'That file is not a collections export.' };
        }
        if (!payload.collections || typeof payload.collections !== 'object') {
            return { ok: false, reason: 'The file has no collections in it.' };
        }

        const current = read();
        let added = 0;
        let merged = 0;

        Object.entries(payload.collections).forEach(([name, agents]) => {
            if (typeof name !== 'string' || !name.trim() || !Array.isArray(agents)) return;

            const clean = agents.filter(a => typeof a === 'string' && a.trim()).slice(0, MAX_AGENTS);
            const key = name.trim();

            if (has(current, key)) {
                const seen = new Set(current[key].map(a => a.toLowerCase()));
                const extra = clean.filter(a => !seen.has(a.toLowerCase()));
                if (extra.length) {
                    current[key] = [...current[key], ...extra].slice(0, MAX_AGENTS);
                    merged += 1;
                }
            } else if (Object.keys(current).length < MAX_COLLECTIONS) {
                current[key] = clean;
                added += 1;
            }
        });

        if (!write(current)) return { ok: false, reason: 'Could not save; storage is unavailable.' };
        return { ok: true, added, merged };
    }

    function clear() {
        try {
            localStorage.removeItem(STORAGE_KEY);
        } catch (error) {
            // read() still returns {} if this fails.
        }
    }

    return {
        STORAGE_KEY, MAX_COLLECTIONS, MAX_AGENTS,
        read, names, agentsIn, create, add, remove, destroy,
        containing, compareUrl, exportAll, exportOne, importAll, clear,
    };
})();

if (typeof module !== 'undefined') module.exports = Collections;
