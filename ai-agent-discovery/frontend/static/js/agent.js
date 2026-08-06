document.addEventListener('DOMContentLoaded', async () => {
    const detail = document.getElementById('agentDetail');
    const similarSection = document.getElementById('similarSection');
    const similarGrid = document.getElementById('similarGrid');

    // The name is the last path segment of /agent/<name>.
    const name = decodeURIComponent(window.location.pathname.split('/').filter(Boolean).pop() || '');

    function showError(text) {
        const p = document.createElement('p');
        p.className = 'result-message error';
        p.textContent = text;
        detail.replaceChildren(p);
        detail.setAttribute('aria-busy', 'false');
    }

    function field(label, value) {
        const row = document.createElement('div');
        row.className = 'detail-row';
        const dt = document.createElement('span');
        dt.className = 'detail-label';
        dt.textContent = label;
        const dd = document.createElement('span');
        dd.className = 'detail-value';
        dd.textContent = value;
        row.append(dt, dd);
        return row;
    }

    function render(agent) {
        const meta = agent.metadata || {};
        const wrapper = document.createElement('article');
        wrapper.className = 'agent-detail';

        const heading = document.createElement('h1');
        heading.textContent = meta.name || agent.name || 'Unknown agent';
        wrapper.appendChild(heading);

        const description = document.createElement('p');
        description.className = 'detail-description';
        description.textContent = meta.description || agent.description || 'No description available.';
        wrapper.appendChild(description);

        wrapper.appendChild(field('Category', meta.category || 'Uncategorized'));
        wrapper.appendChild(field('GitHub stars', AgentCard.formatStars(meta.stars)));

        const stack = AgentCard.parseStack(meta.stack).map(t => String(t).trim()).filter(Boolean);
        if (stack.length) {
            const row = document.createElement('div');
            row.className = 'detail-row';
            const label = document.createElement('span');
            label.className = 'detail-label';
            label.textContent = 'Tech stack';
            const chips = document.createElement('span');
            chips.className = 'tech-stack';
            stack.forEach(tech => {
                const chip = document.createElement('span');
                chip.className = 'tech-item';
                chip.textContent = tech;
                chips.appendChild(chip);
            });
            row.append(label, chips);
            wrapper.appendChild(row);
        }

        const href = AgentCard.safeUrl(meta.url);
        if (href) {
            const link = document.createElement('a');
            link.className = 'view-btn';
            link.href = href;
            link.target = '_blank';
            link.rel = 'noopener noreferrer';
            link.textContent = 'Visit project →';
            wrapper.appendChild(link);
        }

        detail.replaceChildren(wrapper);
        detail.setAttribute('aria-busy', 'false');
    }

    async function loadSimilar(agent) {
        const meta = agent.metadata || {};
        const query = meta.description || agent.description || meta.name;
        if (!query) return;

        try {
            const response = await fetch('/api/search', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query, limit: 4 })
            });
            if (!response.ok) return;

            const data = await response.json();
            // Drop the agent itself from its own "similar" list.
            const others = (data.results || []).filter(r => r.name !== agent.name).slice(0, 3);
            if (others.length === 0) return;

            AgentCard.renderGrid(similarGrid, others);
            similarSection.hidden = false;
        } catch (error) {
            console.error('Could not load similar agents:', error);
        }
    }

    if (!name) {
        showError('No agent specified.');
        return;
    }

    try {
        const response = await fetch(`/api/agents/${encodeURIComponent(name)}`);
        if (response.status === 404) {
            showError(`No agent named "${name}".`);
            return;
        }
        if (!response.ok) throw new Error(`Request failed with status ${response.status}`);

        const agent = await response.json();
        document.getElementById('crumbName').textContent = agent.name;
        document.title = `${agent.name} | AI Agent Discovery`;
        render(agent);
        loadSimilar(agent);
    } catch (error) {
        console.error(error);
        showError('Could not load this agent.');
    }
});
