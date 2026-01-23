document.addEventListener('DOMContentLoaded', () => {
    const searchInput = document.getElementById('searchInput');
    const searchBtn = document.getElementById('searchBtn');
    const resultsArea = document.getElementById('resultsArea');
    const filterTags = document.querySelectorAll('.filter-tag');

    // Initial load - maybe load some random or top agents?
    // For now, let's wait for user input.

    async function performSearch(query) {
        if (!query.trim()) return;

        // Show loading
        resultsArea.innerHTML = `
            <div class="loading">
                <div class="spinner"></div>
                <p>Searching the agentverse...</p>
            </div>
        `;

        try {
            const response = await fetch('/api/search', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ query })
            });

            const data = await response.json();

            if (data.results) {
                renderResults(data.results);
            } else {
                resultsArea.innerHTML = '<p style="text-align: center; color: var(--text-secondary);">No agents found.</p>';
            }
        } catch (error) {
            console.error('Error:', error);
            resultsArea.innerHTML = '<p style="text-align: center; color: #ef4444;">An error occurred while searching.</p>';
        }
    }

    function renderResults(agents) {
        if (agents.length === 0) {
            resultsArea.innerHTML = '<p style="text-align: center; color: var(--text-secondary);">No agents found matching your query.</p>';
            return;
        }

        const grid = document.createElement('div');
        grid.className = 'results-grid';

        agents.forEach(agent => {
            const card = document.createElement('div');
            card.className = 'agent-card';
            
            // Handle parsing tech stack if it comes as a string or list
            let stack = agent.metadata.stack;
            if (typeof stack === 'string') {
                stack = stack.split(',');
            }
            const stackHtml = stack.map(tech => `<span class="tech-item">${tech.trim()}</span>`).join('');

            card.innerHTML = `
                <div class="card-header">
                    <div class="agent-name">${agent.metadata.name}</div>
                    <div class="agent-category">${agent.metadata.category}</div>
                </div>
                <!-- Note: using description from vector search result which might be the page_content. 
                     Ideally we should accept structured data back. 
                     The current vectorstore returns 'description' as full text. 
                     Let's use a regex or just substring for now to clean it up if needed.
                     Actually, let's just use metadata description if available? 
                     The current 'agent.description' in results is the page_content.
                -->
                <div class="agent-description">
                    ${agent.metadata.description || extractDescription(agent.description)}
                </div>
                <div class="tech-stack">
                    ${stackHtml}
                </div>
                <div class="card-footer">
                    <div class="stars">
                        <ion-icon name="star"></ion-icon>
                        <span>${formatStars(agent.metadata.stars)}</span>
                    </div>
                    <a href="${agent.metadata.url || '#'}" target="_blank" class="view-btn">View Agent &rarr;</a>
                </div>
            `;
            grid.appendChild(card);
        });

        resultsArea.innerHTML = '';
        resultsArea.appendChild(grid);
    }

    function extractDescription(fullText) {
        // Fallback to try to extract description from "Description: ..." text
        const match = fullText.match(/Description: (.*?)(?:\n|$)/);
        return match ? match[1] : fullText.substring(0, 100) + '...';
    }

    function formatStars(stars) {
        if (!stars) return 'N/A';
        if (stars >= 1000) return (stars / 1000).toFixed(1) + 'k';
        return stars;
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
