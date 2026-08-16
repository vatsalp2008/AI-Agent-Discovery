/**
 * Pure helpers for the dashboard.
 *
 * Kept out of dashboard.js's DOMContentLoaded closure so the number
 * formatting and paging arithmetic can be tested directly.
 */
const DashboardStats = (() => {
    /** Compact star totals: 1234 -> "1.2k", 1500000 -> "1.5M+". */
    function formatTotal(stars) {
        const value = Number(stars);
        if (!value || Number.isNaN(value) || value < 0) return '0';
        if (value >= 1000000) return (value / 1000000).toFixed(1) + 'M+';
        if (value >= 1000) return (value / 1000).toFixed(1) + 'k';
        return String(Math.round(value));
    }

    /** The three headline figures, tolerant of a partial /api/stats payload. */
    function headline(stats) {
        const s = stats || {};
        return {
            total: s.count == null ? '-' : String(s.count),
            topCategory: s.top_category ? s.top_category.name : 'N/A',
            stars: formatTotal(s.total_stars || 0),
        };
    }

    /** Label for the "load more" control, or null when the page is complete. */
    function loadMoreLabel(shown, metadata) {
        const meta = metadata || {};
        if (!meta.has_more) return null;
        return `Load more (${shown} of ${meta.total})`;
    }

    /** Message shown once every agent is on screen. */
    function completeMessage(metadata) {
        const total = (metadata || {}).total || 0;
        if (total === 0) return null;
        return `Showing all ${total} agents.`;
    }

    /**
     * Query string for a page, carrying whatever filters are active.
     * Empty filters are omitted rather than sent blank.
     */
    function pageQuery(offset, pageSize, filters = {}) {
        const params = new URLSearchParams({ limit: pageSize, offset });
        ['q', 'category', 'tech', 'maintained', 'sort', 'order'].forEach(key => {
            const value = filters[key];
            if (value) params.set(key, value);
        });
        return `?${params.toString()}`;
    }

    return { formatTotal, headline, loadMoreLabel, completeMessage, pageQuery };
})();
