document.addEventListener('DOMContentLoaded', () => {
    const searchInput = document.getElementById('searchInput');
    const searchBtn = document.getElementById('searchBtn');
    const resultsArea = document.getElementById('resultsArea');
    const filterTags = document.querySelectorAll('.filter-tag');

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

        try {
            const response = await fetch('/api/search', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ query })
            });

            const data = await response.json();

            if (!response.ok) {
                showMessage(data.error || 'Search failed.', true);
                return;
            }

            if (Array.isArray(data.results) && data.results.length > 0) {
                AgentCard.renderGrid(resultsArea, data.results);
            } else {
                showMessage('No agents found matching your query.');
            }
        } catch (error) {
            console.error('Error:', error);
            showMessage('An error occurred while searching.', true);
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

    filterTags.forEach(tag => {
        tag.addEventListener('click', () => {
            const query = tag.dataset.query;
            searchInput.value = query;
            performSearch(query);

            // Active state
            filterTags.forEach(t => t.classList.remove('active'));
            tag.classList.add('active');
        });
    });
});
