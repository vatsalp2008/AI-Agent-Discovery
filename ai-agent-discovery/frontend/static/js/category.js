document.addEventListener('DOMContentLoaded', async () => {
    const grid = document.getElementById('categoryGrid');
    const countEl = document.getElementById('categoryCount');
    const otherEl = document.getElementById('categoryOther');

    // The name is the last path segment of /category/<name>. A malformed
    // escape (/category/100%) makes decodeURIComponent throw, which would
    // otherwise kill the whole handler and leave the page saying "Loading…".
    const rawSegment = window.location.pathname.split('/').filter(Boolean).pop() || '';
    let name;
    try {
        name = decodeURIComponent(rawSegment);
    } catch (error) {
        name = rawSegment;
    }

    function message(text, subtitle) {
        const p = document.createElement('p');
        p.className = 'result-message';
        p.textContent = text;
        grid.replaceChildren(p);
        grid.setAttribute('aria-busy', 'false');
        // Never leave the header stuck on "Loading…".
        if (countEl) countEl.textContent = subtitle || '';
    }

    /** Links to the other categories, so this is a place to browse from. */
    async function loadOthers() {
        try {
            const response = await fetch('/api/categories');
            if (!response.ok) return;

            const categories = await response.json();
            if (!Array.isArray(categories)) return;

            categories
                .filter(c => c.name.toLowerCase() !== name.toLowerCase())
                .forEach(c => {
                    const link = document.createElement('a');
                    link.className = 'filter-tag';
                    link.href = `/category/${encodeURIComponent(c.name)}`;
                    link.textContent = `${c.name} (${c.count})`;
                    otherEl.appendChild(link);
                });
        } catch (error) {
            console.error('Could not load categories:', error);
        }
    }

    if (!name) {
        message('No category specified.', '');
        return;
    }

    try {
        // Paged: a category could hold more agents than one page returns.
        const body = await AgentsApi.fetchAll({ category: name, sort: 'stars' });
        if (body.failed) throw new Error('Could not load this category.');
        const agents = body.agents || [];

        if (agents.length === 0) {
            message(`Nothing is filed under "${name}".`, 'No agents in this category.');
            loadOthers();
            return;
        }

        // body.total is the size of the whole category; agents.length is only
        // what was fetched.
        const total = body.total ?? agents.length;
        countEl.textContent = `${total} agent${total === 1 ? '' : 's'}, most starred first`;
        AgentCard.renderGrid(grid, agents);
        grid.setAttribute('aria-busy', 'false');
    } catch (error) {
        console.error(error);
        message('Could not load this category.', 'Could not load.');
    }

    loadOthers();
});
