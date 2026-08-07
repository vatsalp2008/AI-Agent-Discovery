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
        // The name links to the in-app detail page; the footer link goes to
        // the external project.
        const nameEl = el('div', 'agent-name');
        if (meta.name) {
            const nameLink = el('a', 'agent-name-link', meta.name);
            nameLink.href = `/agent/${encodeURIComponent(meta.name)}`;
            nameEl.appendChild(nameLink);
        } else {
            nameEl.textContent = 'Unnamed agent';
        }
        header.appendChild(nameEl);
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

    /**
     * A link that compares `agent` against the others shown alongside it.
     * Returns null when there is nothing to compare against.
     */
    function compareLink(agent, siblings) {
        const name = (agent.metadata || {}).name || agent.name;
        if (!name) return null;

        const others = (siblings || [])
            .map(s => (s.metadata || {}).name || s.name)
            .filter(n => n && n !== name)
            .slice(0, 2);
        if (others.length === 0) return null;

        const link = el('a', 'compare-link', 'Compare');
        link.href = `/compare?names=${encodeURIComponent([name, ...others].join(','))}`;
        link.title = `Compare ${name} with ${others.join(' and ')}`;
        return link;
    }

    /** Replace the contents of `container` with a grid of agent cards. */
    function renderGrid(container, agents) {
        const grid = el('div', 'results-grid');
        agents.forEach(agent => {
            const card = create(agent);
            const compare = compareLink(agent, agents);
            if (compare) {
                const footer = card.querySelector('.card-footer');
                if (footer) footer.insertBefore(compare, footer.lastChild);
            }
            grid.appendChild(card);
        });
        container.replaceChildren(grid);
        return grid;
    }

    return { create, renderGrid, compareLink, formatStars, parseStack, safeUrl };
})();
