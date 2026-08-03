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

    function summarize(agents) {
        const categories = {};
        let stars = 0;
        agents.forEach(agent => {
            const meta = agent.metadata || {};
            const category = meta.category || 'Uncategorized';
            categories[category] = (categories[category] || 0) + 1;
            stars += Number(meta.stars) || 0;
        });
        const ranked = Object.entries(categories).sort((a, b) => b[1] - a[1]);
        return {
            total: agents.length,
            topCategory: ranked.length > 0 ? ranked[0][0] : 'N/A',
            stars
        };
    }

    function showMessage(text) {
        const p = document.createElement('p');
        p.className = 'result-message error';
        p.textContent = text;
        grid.replaceChildren(p);
    }

    try {
        const response = await fetch('/api/agents');
        if (!response.ok) throw new Error(`Request failed with status ${response.status}`);

        const payload = await response.json();
        const agents = Array.isArray(payload) ? payload : (payload.agents || []);

        const stats = summarize(agents);
        totalAgentsEl.textContent = stats.total;
        topCategoryEl.textContent = stats.topCategory;
        totalStarsEl.textContent = formatTotalStars(stats.stars);

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
