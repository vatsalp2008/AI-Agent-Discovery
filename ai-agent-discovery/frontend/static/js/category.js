document.addEventListener('DOMContentLoaded', async () => {
    const grid = document.getElementById('categoryGrid');
    const countEl = document.getElementById('categoryCount');
    const otherEl = document.getElementById('categoryOther');

    // The name is the last path segment of /category/<name>.
    const name = decodeURIComponent(window.location.pathname.split('/').filter(Boolean).pop() || '');

    function message(text) {
        const p = document.createElement('p');
        p.className = 'result-message';
        p.textContent = text;
        grid.replaceChildren(p);
        grid.setAttribute('aria-busy', 'false');
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
        message('No category specified.');
        return;
    }

    try {
        const response = await fetch(
            `/api/agents?category=${encodeURIComponent(name)}&limit=200&sort=stars`);
        if (!response.ok) throw new Error(`Request failed with status ${response.status}`);

        const body = await response.json();
        const agents = body.agents || [];

        if (agents.length === 0) {
            countEl.textContent = 'No agents in this category.';
            message(`Nothing is filed under "${name}".`);
            loadOthers();
            return;
        }

        countEl.textContent = `${agents.length} agent${agents.length === 1 ? '' : 's'}, most starred first`;
        AgentCard.renderGrid(grid, agents);
        grid.setAttribute('aria-busy', 'false');
    } catch (error) {
        console.error(error);
        message('Could not load this category.');
    }

    loadOthers();
});
