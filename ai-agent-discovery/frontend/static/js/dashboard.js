document.addEventListener('DOMContentLoaded', async () => {
    const totalAgentsEl = document.getElementById('totalAgents');
    const topCategoryEl = document.getElementById('topCategory');
    const totalStarsEl = document.getElementById('totalStars');
    const grid = document.getElementById('allAgentsGrid');

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
    }

    try {
        // Stats are computed server-side; this page only needs the totals
        // plus the agent list itself.
        const [statsResponse, agentsResponse] = await Promise.all([
            fetch('/api/stats'),
            fetch('/api/agents')
        ]);
        if (!agentsResponse.ok) throw new Error(`Request failed with status ${agentsResponse.status}`);

        if (statsResponse.ok) {
            const stats = await statsResponse.json();
            totalAgentsEl.textContent = stats.count;
            topCategoryEl.textContent = stats.top_category ? stats.top_category.name : 'N/A';
            totalStarsEl.textContent = formatTotalStars(stats.total_stars || 0);
        }

        const payload = await agentsResponse.json();
        const agents = Array.isArray(payload) ? payload : (payload.agents || []);

        if (agents.length === 0) {
            showMessage('No agents indexed yet. Run seed.py to populate the vector store.');
            return;
        }

        grid.replaceChildren();
        agents.forEach(agent => grid.appendChild(AgentCard.create(agent)));
    } catch (error) {
        console.error(error);
        showMessage('Error loading dashboard data.');
    }
});
