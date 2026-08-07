document.addEventListener('DOMContentLoaded', async () => {
    const totalAgentsEl = document.getElementById('totalAgents');
    const topCategoryEl = document.getElementById('topCategory');
    const totalStarsEl = document.getElementById('totalStars');
    const grid = document.getElementById('allAgentsGrid');
    const footer = document.getElementById('gridFooter');
    const statsGrid = document.getElementById('statsGrid');

    const PAGE_SIZE = 24;
    let offset = 0;

    const controls = {
        q: document.getElementById('filterQuery'),
        category: document.getElementById('filterCategory'),
        tech: document.getElementById('filterTech'),
        sort: document.getElementById('sortBy'),
        order: document.getElementById('sortOrder'),
    };
    let order = 'asc';

    function activeFilters() {
        return {
            q: controls.q ? controls.q.value.trim() : '',
            category: controls.category ? controls.category.value : '',
            tech: controls.tech ? controls.tech.value : '',
            sort: controls.sort ? controls.sort.value : 'name',
            order,
        };
    }

    /** Populate a <select> from a [{name, count}] facet list. */
    async function fillFacet(select, url) {
        if (!select) return;
        try {
            const response = await fetch(url);
            if (!response.ok) return;
            const items = await response.json();
            if (!Array.isArray(items)) return;
            items.forEach(item => {
                const option = document.createElement('option');
                option.value = item.name;
                option.textContent = `${item.name} (${item.count})`;
                select.appendChild(option);
            });
        } catch (error) {
            console.error(`Could not load facets from ${url}:`, error);
        }
    }

    /** Re-run the listing from the first page with the current filters. */
    async function applyFilters() {
        offset = 0;
        grid.replaceChildren();
        grid.setAttribute('aria-busy', 'true');
        footer.replaceChildren();
        try {
            await loadPage();
        } catch (error) {
            console.error(error);
            showMessage('Error loading dashboard data.');
        } finally {
            grid.setAttribute('aria-busy', 'false');
        }
    }

    function showMessage(text) {
        const p = document.createElement('p');
        p.className = 'result-message error';
        p.textContent = text;
        grid.replaceChildren(p);
        grid.setAttribute('aria-busy', 'false');
        statsGrid.setAttribute('aria-busy', 'false');
        footer.replaceChildren();
    }

    /** Append one page of agents, and offer the next if there is one. */
    function renderPage(agents, metadata) {
        const previousCount = grid.children.length;
        agents.forEach(agent => grid.appendChild(AgentCard.create(agent)));
        offset += agents.length;
        footer.replaceChildren();

        const label = DashboardStats.loadMoreLabel(offset, metadata);
        if (label) {
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'load-more';
            button.textContent = label;
            button.addEventListener('click', async () => {
                button.disabled = true;
                button.textContent = 'Loading…';
                grid.setAttribute('aria-busy', 'true');
                try {
                    await loadPage();
                    // Move focus to the first newly added card so keyboard
                    // users are not dropped back at the top of the document.
                    const firstNew = grid.children[previousCount];
                    if (firstNew) {
                        firstNew.tabIndex = -1;
                        firstNew.focus();
                    }
                } catch (error) {
                    console.error(error);
                    button.disabled = false;
                    button.textContent = 'Retry';
                } finally {
                    grid.setAttribute('aria-busy', 'false');
                }
            });
            footer.appendChild(button);
        } else {
            const complete = DashboardStats.completeMessage(metadata);
            if (complete) {
                const done = document.createElement('p');
                done.className = 'result-message';
                done.textContent = complete;
                footer.appendChild(done);
            }
        }
    }

    async function loadPage() {
        const response = await fetch('/api/agents' + DashboardStats.pageQuery(offset, PAGE_SIZE, activeFilters()));
        if (!response.ok) throw new Error(`Request failed with status ${response.status}`);

        const payload = await response.json();
        const agents = payload.agents || [];
        if (offset === 0 && agents.length === 0) {
            showMessage('No agents match these filters.');
            return;
        }
        renderPage(agents, payload.metadata || {});
    }

    try {
        // Stats are computed server-side; this page only needs the totals
        // plus one page of agents at a time.
        const [statsResponse, agentsResponse] = await Promise.all([
            fetch('/api/stats'),
            fetch('/api/agents' + DashboardStats.pageQuery(0, PAGE_SIZE, activeFilters()))
        ]);
        if (!agentsResponse.ok) throw new Error(`Request failed with status ${agentsResponse.status}`);

        if (statsResponse.ok) {
            const headline = DashboardStats.headline(await statsResponse.json());
            totalAgentsEl.textContent = headline.total;
            topCategoryEl.textContent = headline.topCategory;
            totalStarsEl.textContent = headline.stars;
        }
        statsGrid.setAttribute('aria-busy', 'false');

        const payload = await agentsResponse.json();
        const agents = payload.agents || [];

        if (agents.length === 0) {
            showMessage('No agents indexed yet. Run seed.py to populate the vector store.');
            return;
        }

        grid.replaceChildren();
        renderPage(agents, payload.metadata || {});
        grid.setAttribute('aria-busy', 'false');

        fillFacet(controls.category, '/api/categories');
        fillFacet(controls.tech, '/api/tech');

        // Typing filters on a short debounce; the selects fire immediately.
        let typingTimer;
        if (controls.q) {
            controls.q.addEventListener('input', () => {
                clearTimeout(typingTimer);
                typingTimer = setTimeout(applyFilters, 250);
            });
        }
        [controls.category, controls.tech, controls.sort].forEach(select => {
            if (select) select.addEventListener('change', applyFilters);
        });
        if (controls.order) {
            controls.order.addEventListener('click', () => {
                order = order === 'asc' ? 'desc' : 'asc';
                controls.order.textContent = order === 'asc' ? '↑' : '↓';
                controls.order.setAttribute('aria-label',
                    order === 'asc' ? 'Sort ascending' : 'Sort descending');
                applyFilters();
            });
        }
    } catch (error) {
        console.error(error);
        showMessage('Error loading dashboard data.');
    }
});
