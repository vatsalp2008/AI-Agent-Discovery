/**
 * Name suggestions for the search box.
 *
 * Deliberately a *complement* to semantic search, not a replacement: it
 * answers "I know roughly what it is called", which embeddings handle less
 * directly than a prefix match. Semantic search still runs on submit.
 *
 * The whole name list is fetched once and matched locally — at a hundred-odd
 * agents that is a few kilobytes, and it keeps keystrokes off the network.
 */
const Suggest = (() => {
    const MAX = 8;

    /**
     * Rank matches for `query`. A name starting with the query beats one
     * merely containing it, so typing "co" offers "ComfyUI" before "Vocode".
     */
    function rank(entries, query, limit = MAX) {
        const needle = (query || '').trim().toLowerCase();
        if (!needle) return [];

        const starts = [];
        const contains = [];
        entries.forEach(entry => {
            const name = String(entry.name || '');
            const lower = name.toLowerCase();
            if (lower.startsWith(needle)) starts.push(entry);
            else if (lower.includes(needle)) contains.push(entry);
        });

        const byName = (a, b) => String(a.name).localeCompare(String(b.name));
        return [...starts.sort(byName), ...contains.sort(byName)].slice(0, limit);
    }

    /** Split a name around the matched span, for highlighting. */
    function segments(name, query) {
        const needle = (query || '').trim().toLowerCase();
        const index = needle ? String(name).toLowerCase().indexOf(needle) : -1;
        if (index < 0) return [{ text: String(name), match: false }];

        const value = String(name);
        return [
            { text: value.slice(0, index), match: false },
            { text: value.slice(index, index + needle.length), match: true },
            { text: value.slice(index + needle.length), match: false },
        ].filter(part => part.text);
    }

    /** Move through the list, wrapping at both ends. -1 means nothing active. */
    function nextIndex(current, count, step) {
        if (count === 0) return -1;
        if (current === -1) return step > 0 ? 0 : count - 1;
        return (current + step + count) % count;
    }

    return { MAX, rank, segments, nextIndex };
})();

if (typeof module !== 'undefined') module.exports = Suggest;
