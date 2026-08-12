/**
 * Fetching agent lists from /api/agents.
 *
 * The server caps `limit` at AGENTS_MAX_PAGE_SIZE, so a single request with a
 * big limit silently truncates — no error, just missing agents once the
 * catalogue outgrows the cap. Three separate callers had that bug, so the
 * paging lives here instead of being repeated.
 */
const AgentsApi = (() => {
    const PAGE_SIZE = 200;
    const MAX_PAGES = 25;      // a runaway has_more must not spin forever

    /** Build a query string from params, omitting empty values. */
    function query(params = {}, extra = {}) {
        const search = new URLSearchParams();
        Object.entries({ ...params, ...extra }).forEach(([key, value]) => {
            if (value !== undefined && value !== null && value !== '') {
                search.set(key, value);
            }
        });
        return search.toString();
    }

    /**
     * Every agent matching `params`, following pagination.
     *
     * Returns `{ agents, total, failed }`. A partial list is kept when a later
     * page fails, but `failed` says so — without it a caller cannot tell an
     * empty category from a request that never arrived, and would report
     * "nothing here" for an outage.
     */
    async function fetchAll(params = {}, { fetchImpl = fetch } = {}) {
        const agents = [];
        let offset = 0;
        let total = null;
        let failed = false;
        let exhausted = false;

        for (let page = 0; page < MAX_PAGES; page += 1) {
            let body;
            try {
                const response = await fetchImpl(
                    `/api/agents?${query(params, { limit: PAGE_SIZE, offset })}`);
                if (!response.ok) {
                    failed = true;
                    break;
                }
                body = await response.json();
            } catch (error) {
                console.error('Could not load agents:', error);
                failed = true;
                break;
            }

            const batch = body.agents || [];
            batch.forEach(a => agents.push(a));

            const metadata = body.metadata || {};
            if (total === null && typeof metadata.total === 'number') total = metadata.total;

            offset += batch.length;
            if (!metadata.has_more || batch.length === 0) break;

            // Still more to come, and this was the last page we will fetch.
            // Report it as a failure: silently returning a truncated list is
            // exactly the mode this module exists to prevent, and a caller
            // would otherwise render 5,000 cards under a "6,000 agents"
            // heading with nothing wrong on screen.
            if (page === MAX_PAGES - 1) {
                console.error(
                    `Stopped after ${MAX_PAGES} pages with more agents remaining; ` +
                    'the list is incomplete.');
                exhausted = true;
            }
        }

        return {
            agents,
            total: total === null ? agents.length : total,
            failed: failed || exhausted,
            exhausted,
        };
    }

    return { PAGE_SIZE, MAX_PAGES, query, fetchAll };
})();

if (typeof module !== 'undefined') module.exports = AgentsApi;
