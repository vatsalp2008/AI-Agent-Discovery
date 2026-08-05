/**
 * Shared agent card rendering.
 *
 * Cards are built with DOM APIs and textContent rather than innerHTML
 * templates: agent records come from data/agents.json, which users are
 * encouraged to extend by hand, so field values must never be treated as
 * markup. Links are restricted to http(s) so a `javascript:` URL in the data
 * cannot become a clickable script.
 */
const AgentCard = (() => {
    const SAFE_PROTOCOLS = ['http:', 'https:'];

    function safeUrl(raw) {
        if (!raw) return null;
        try {
            // Parsed without a base, so a relative or malformed value throws
            // rather than silently resolving to a same-origin link. Agent URLs
            // are meant to be absolute project homepages.
            const url = new URL(raw);
            return SAFE_PROTOCOLS.includes(url.protocol) ? url.href : null;
        } catch (err) {
            return null;
        }
    }

    function formatStars(stars) {
        const value = Number(stars);
        if (!value || Number.isNaN(value)) return 'N/A';
        if (value >= 1000) return (value / 1000).toFixed(1) + 'k';
        return String(value);
    }

    function parseStack(stack) {
        if (Array.isArray(stack)) return stack;
        if (typeof stack === 'string') return stack.split(',');
        return [];
    }

    function el(tag, className, text) {
        const node = document.createElement(tag);
        if (className) node.className = className;
        if (text !== undefined && text !== null) node.textContent = text;
        return node;
    }

    function create(agent) {
        const meta = agent.metadata || {};
        const card = el('div', 'agent-card');

        const header = el('div', 'card-header');
        header.appendChild(el('div', 'agent-name', meta.name || 'Unnamed agent'));
        header.appendChild(el('div', 'agent-category', meta.category || 'Uncategorized'));
        card.appendChild(header);

        if (typeof agent.score === 'number') {
            const match = el('div', 'match-score', `${Math.round(agent.score * 100)}% match`);
            match.title = 'Semantic relevance to your query';
            card.appendChild(match);
        }

        const description = meta.description || agent.description || 'No description available.';
        card.appendChild(el('div', 'agent-description', description));

        const stack = el('div', 'tech-stack');
        parseStack(meta.stack)
            .map(tech => String(tech).trim())
            .filter(Boolean)
            .forEach(tech => stack.appendChild(el('span', 'tech-item', tech)));
        card.appendChild(stack);

        const footer = el('div', 'card-footer');
        const stars = el('div', 'stars');
        const icon = document.createElement('ion-icon');
        icon.setAttribute('name', 'star');
        stars.appendChild(icon);
        stars.appendChild(el('span', null, formatStars(meta.stars)));
        footer.appendChild(stars);

        const href = safeUrl(meta.url);
        const link = el('a', 'view-btn', 'View Agent →');
        if (href) {
            link.href = href;
            link.target = '_blank';
            link.rel = 'noopener noreferrer';
        } else {
            link.classList.add('disabled');
            link.setAttribute('aria-disabled', 'true');
        }
        footer.appendChild(link);
        card.appendChild(footer);

        return card;
    }

    /** Replace the contents of `container` with a grid of agent cards. */
    function renderGrid(container, agents) {
        const grid = el('div', 'results-grid');
        agents.forEach(agent => grid.appendChild(create(agent)));
        container.replaceChildren(grid);
        return grid;
    }

    return { create, renderGrid, formatStars, parseStack, safeUrl };
})();
