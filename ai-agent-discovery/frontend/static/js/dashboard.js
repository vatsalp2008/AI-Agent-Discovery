document.addEventListener('DOMContentLoaded', async () => {
    const totalAgentsEl = document.getElementById('totalAgents');
    const topCategoryEl = document.getElementById('topCategory');
    const totalStarsEl = document.getElementById('totalStars');
    const grid = document.getElementById('allAgentsGrid');
    const footer = document.getElementById('gridFooter');
    const statsGrid = document.getElementById('statsGrid');

    const PAGE_SIZE = 24;
    let offset = 0;

    function formatTotalStars(stars) {
        if (stars >= 1000000) return (stars / 1000000).toFixed(1) + 'M+';
        if (stars >= 1000) return (stars / 1000).toFixed(1) + 'k';
        return String(stars);
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

        if (metadata.has_more) {
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'load-more';
            button.textContent = `Load more (${offset} of ${metadata.total})`;
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
        } else if (metadata.total > 0) {
            const done = document.createElement('p');
            done.className = 'result-message';
            done.textContent = `Showing all ${metadata.total} agents.`;
            footer.appendChild(done);
        }
    }

    async function loadPage() {
        const response = await fetch(`/api/agents?limit=${PAGE_SIZE}&offset=${offset}`);
        if (!response.ok) throw new Error(`Request failed with status ${response.status}`);

        const payload = await response.json();
        renderPage(payload.agents || [], payload.metadata || {});
    }

    try {
        // Stats are computed server-side; this page only needs the totals
        // plus one page of agents at a time.
        const [statsResponse, agentsResponse] = await Promise.all([
            fetch('/api/stats'),
            fetch(`/api/agents?limit=${PAGE_SIZE}&offset=0`)
        ]);
        if (!agentsResponse.ok) throw new Error(`Request failed with status ${agentsResponse.status}`);

        if (statsResponse.ok) {
            const stats = await statsResponse.json();
            totalAgentsEl.textContent = stats.count;
            topCategoryEl.textContent = stats.top_category ? stats.top_category.name : 'N/A';
            totalStarsEl.textContent = formatTotalStars(stats.total_stars || 0);
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
    } catch (error) {
        console.error(error);
        showMessage('Error loading dashboard data.');
    }
});
