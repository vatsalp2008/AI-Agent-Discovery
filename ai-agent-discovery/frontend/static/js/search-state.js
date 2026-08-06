/**
 * Pure helpers for search state and request shaping.
 *
 * Kept out of main.js's DOMContentLoaded closure so the URL round-trip and
 * request-body rules can be tested directly, without a page.
 */
const SearchState = (() => {
    /** Parse a location.search string into {query, category}. */
    function fromSearch(search) {
        const params = new URLSearchParams(search || '');
        const query = (params.get('q') || '').trim();
        const category = (params.get('category') || '').trim();
        return { query, category: category || null };
    }

    /**
     * Build the URL for a given state. Returns just the pathname when there
     * is nothing to encode, so a cleared search does not leave a bare "?".
     */
    function toUrl(pathname, { query, category } = {}) {
        const params = new URLSearchParams();
        if (query) params.set('q', query);
        if (category) params.set('category', category);

        const search = params.toString();
        return search ? `${pathname}?${search}` : pathname;
    }

    /** Body for POST /api/search. Optional fields are omitted, not sent null. */
    function searchBody({ query, category, summarize } = {}) {
        const body = { query };
        if (category) body.category = category;
        if (summarize) body.summarize = true;
        return body;
    }

    /** Message to show when a search returns nothing. */
    function emptyMessage(category) {
        return category
            ? `No agents in "${category}" match your query.`
            : 'No agents found matching your query.';
    }

    return { fromSearch, toUrl, searchBody, emptyMessage };
})();
