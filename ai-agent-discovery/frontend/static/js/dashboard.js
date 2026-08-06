document.addEventListener('DOMContentLoaded', async () => {
    const totalAgentsEl = document.getElementById('totalAgents');
    const topCategoryEl = document.getElementById('topCategory');
    const totalStarsEl = document.getElementById('totalStars');
    const grid = document.getElementById('allAgentsGrid');
    const footer = document.getElementById('gridFooter');
    const statsGrid = document.getElementById('statsGrid');

    const PAGE_SIZE = 24;
    let offset = 0;

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
        const response = await fetch('/api/agents' + DashboardStats.pageQuery(offset, PAGE_SIZE));
        if (!response.ok) throw new Error(`Request failed with status ${response.status}`);

        const payload = await response.json();
        renderPage(payload.agents || [], payload.metadata || {});
    }

    try {
        // Stats are computed server-side; this page only needs the totals
        // plus one page of agents at a time.
        const [statsResponse, agentsResponse] = await Promise.all([
            fetch('/api/stats'),
            fetch('/api/agents' + DashboardStats.pageQuery(0, PAGE_SIZE))
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
    } catch (error) {
        console.error(error);
        showMessage('Error loading dashboard data.');
    }
});
