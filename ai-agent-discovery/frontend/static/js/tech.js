/**
 * Everything built with one technology.
 *
 * The mirror of the category page. Categories answer "what does this do";
 * technologies answer "what will this fit into", which is the other question
 * somebody has when choosing between two agents that do the same job.
 */
document.addEventListener('DOMContentLoaded', async () => {
    const grid = document.getElementById('techGrid');
    const countEl = document.getElementById('techCount');
    const otherEl = document.getElementById('techOther');

    // The name is the last path segment of /tech/<name>. A malformed escape
    // (/tech/100%) makes decodeURIComponent throw, which would otherwise kill
    // the handler and leave the page saying "Loading…".
    const rawSegment = window.location.pathname.split('/').filter(Boolean).pop() || '';
    let name;
    try {
        name = decodeURIComponent(rawSegment);
    } catch (error) {
        name = rawSegment;
    }

    function message(text, subtitle) {
        UI.showMessage(grid, text);
        // Never leave the header stuck on "Loading…".
        if (countEl) countEl.textContent = subtitle || '';
    }

    /** Links to the other technologies, so this is a place to browse from. */
    async function loadOthers(limit = 24) {
        try {
            const response = await fetch('/api/tech');
            if (!response.ok) return;

            const technologies = await response.json();
            if (!Array.isArray(technologies)) return;

            // Capped: the catalogue has well over a hundred technologies, and
            // a wall of them is not navigation. /api/tech is sorted by count,
            // so this keeps the ones worth browsing to.
            technologies
                .filter(t => t.name.toLowerCase() !== name.toLowerCase())
                .slice(0, limit)
                .forEach(t => {
                    const link = document.createElement('a');
                    link.className = 'filter-tag';
                    link.href = `/tech/${encodeURIComponent(t.name)}`;
                    link.textContent = `${t.name} (${t.count})`;
                    otherEl.appendChild(link);
                });
        } catch (error) {
            console.error('Could not load technologies:', error);
        }
    }

    if (!name) {
        message('No technology specified.', '');
        return;
    }

    try {
        // Paged: a common technology covers more agents than one page returns.
        const body = await AgentsApi.fetchAll({ tech: name, sort: 'stars' });
        if (body.failed) throw new Error('Could not load this technology.');
        const agents = body.agents || [];

        if (agents.length === 0) {
            message(`Nothing in the catalogue uses "${name}".`,
                    'No agents use this technology.');
            loadOthers();
            return;
        }

        const total = body.total ?? agents.length;
        countEl.textContent = `${total} agent${total === 1 ? '' : 's'} built with ${name}, `
            + 'most starred first';
        AgentCard.renderGrid(grid, agents);
        grid.setAttribute('aria-busy', 'false');
    } catch (error) {
        console.error(error);
        message('Could not load this technology.', 'Could not load.');
    }

    loadOthers();
});
