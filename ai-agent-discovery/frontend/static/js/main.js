document.addEventListener('DOMContentLoaded', () => {
    const searchInput = document.getElementById('searchInput');
    const searchBtn = document.getElementById('searchBtn');
    const resultsArea = document.getElementById('resultsArea');
    const filters = document.getElementById('filters');

    // Category chips act as a real server-side filter, not just a canned query.
    let activeCategory = null;

    function showMessage(text, isError) {
        const p = document.createElement('p');
        p.className = isError ? 'result-message error' : 'result-message';
        p.textContent = text;
        resultsArea.replaceChildren(p);
    }

    function showLoading() {
        const wrapper = document.createElement('div');
        wrapper.className = 'loading';
        wrapper.appendChild(Object.assign(document.createElement('div'), { className: 'spinner' }));
        const label = document.createElement('p');
        label.textContent = 'Searching the agentverse...';
        wrapper.appendChild(label);
        resultsArea.replaceChildren(wrapper);
    }

    async function performSearch(query) {
        if (!query.trim()) return;

        showLoading();

        const body = { query };
        if (activeCategory) body.category = activeCategory;

        try {
            const response = await fetch('/api/search', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(body)
            });

            const data = await response.json();

            if (!response.ok) {
                showMessage(data.error || 'Search failed.', true);
                return;
            }

            if (Array.isArray(data.results) && data.results.length > 0) {
                AgentCard.renderGrid(resultsArea, data.results);
            } else if (activeCategory) {
                showMessage(`No agents in "${activeCategory}" match your query.`);
            } else {
                showMessage('No agents found matching your query.');
            }
        } catch (error) {
            console.error('Error:', error);
            showMessage('An error occurred while searching.', true);
        }
    }

    function makeChip(name, count) {
        const chip = document.createElement('span');
        chip.className = 'filter-tag';
        chip.textContent = count === undefined ? name : `${name} (${count})`;
        chip.dataset.category = name;
        chip.addEventListener('click', () => {
            const wasActive = chip.classList.contains('active');
            filters.querySelectorAll('.filter-tag').forEach(t => t.classList.remove('active'));

            if (wasActive) {
                activeCategory = null;
            } else {
                activeCategory = name;
                chip.classList.add('active');
            }

            if (searchInput.value.trim()) {
                performSearch(searchInput.value);
            }
        });
        return chip;
    }

    async function loadCategories() {
        try {
            const response = await fetch('/api/categories');
            if (!response.ok) return;
            const categories = await response.json();
            if (!Array.isArray(categories) || categories.length === 0) return;
            categories.forEach(c => filters.appendChild(makeChip(c.name, c.count)));
        } catch (error) {
            console.error('Could not load categories:', error);
        }
    }

    /**
     * Fill the empty results area on first visit so the page is not blank
     * before the user has typed anything.
     */
    async function loadInitialAgents() {
        try {
            const response = await fetch('/api/agents?limit=6');
            if (!response.ok) return;

            const body = await response.json();
            const agents = body.agents || [];

            if (agents.length === 0) {
                showMessage('No agents indexed yet. Run seed.py to populate the vector store.');
                return;
            }

            const heading = document.createElement('h2');
            heading.className = 'results-heading';
            heading.textContent = body.metadata.has_more
                ? `Browsing ${agents.length} of ${body.metadata.total} agents`
                : 'Browse agents';

            AgentCard.renderGrid(resultsArea, agents);
            resultsArea.prepend(heading);
        } catch (error) {
            console.error('Could not load agents:', error);
        }
    }

    // Event Listeners
    searchBtn.addEventListener('click', () => {
        performSearch(searchInput.value);
    });

    searchInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            performSearch(searchInput.value);
        }
    });

    loadCategories();
    loadInitialAgents();
});
