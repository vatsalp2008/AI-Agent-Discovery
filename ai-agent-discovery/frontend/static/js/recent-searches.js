/**
 * A short history of recent queries, kept in localStorage.
 *
 * Deliberately client-side only: the project's whole premise is that queries
 * never leave the machine, so sending them to the server to remember would
 * undercut it.
 */
const RecentSearches = (() => {
    const STORAGE_KEY = 'agentdiscovery:recent';
    const LIMIT = 8;

    function read() {
        try {
            const raw = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
            if (!Array.isArray(raw)) return [];
            // Tolerate anything hand-edited or written by an older version.
            return raw
                .filter(entry => entry && typeof entry.query === 'string' && entry.query.trim())
                .slice(0, LIMIT);
        } catch (error) {
            return [];
        }
    }

    function write(entries) {
        try {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(entries.slice(0, LIMIT)));
        } catch (error) {
            // Storage full or unavailable; history is a convenience, not state.
        }
    }

    /** Record a search, most recent first, without duplicates. */
    function add(query, category) {
        const trimmed = (query || '').trim();
        if (!trimmed) return read();

        const key = trimmed.toLowerCase();
        const rest = read().filter(e => e.query.toLowerCase() !== key);
        const entries = [{ query: trimmed, category: category || null }, ...rest];
        write(entries);
        return entries.slice(0, LIMIT);
    }

    function clear() {
        try {
            localStorage.removeItem(STORAGE_KEY);
        } catch (error) {
            // Nothing to do; read() will still return [] on failure.
        }
    }

    /** A label including the category, when one was applied. */
    function label(entry) {
        return entry.category ? `${entry.query} · ${entry.category}` : entry.query;
    }

    return { STORAGE_KEY, LIMIT, read, add, clear, label };
})();

if (typeof module !== 'undefined') module.exports = RecentSearches;
