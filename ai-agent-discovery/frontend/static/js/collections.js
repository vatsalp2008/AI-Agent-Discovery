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

    function read() {
        try {
            const raw = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
            if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return {};

            // Tolerate anything hand-edited or written by an older version.
            const clean = {};
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
        if (Object.keys(collections).length >= MAX_COLLECTIONS && !(trimmed in collections)) {
            return { ok: false, reason: `You can keep at most ${MAX_COLLECTIONS} collections.` };
        }
        if (trimmed in collections) return { ok: false, reason: 'That collection already exists.' };

        collections[trimmed] = [];
        return write(collections)
            ? { ok: true, name: trimmed }
            : { ok: false, reason: 'Could not save; browser storage is unavailable.' };
    }

    function add(name, agent) {
        const collections = read();
        if (!(name in collections)) return { ok: false, reason: 'No such collection.' };

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
        if (!(name in collections)) return { ok: false, reason: 'No such collection.' };

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
        containing, compareUrl, clear,
    };
})();

if (typeof module !== 'undefined') module.exports = Collections;
