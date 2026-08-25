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
        // The category links to its browse page.
        const categoryEl = el('div', 'agent-category');
        if (meta.category) {
            const link = el('a', 'agent-category-link', meta.category);
            link.href = `/category/${encodeURIComponent(meta.category)}`;
            categoryEl.appendChild(link);
        } else {
            categoryEl.textContent = 'Uncategorized';
        }
        header.appendChild(categoryEl);
        card.appendChild(header);

        // Only shown when it is not "active": a badge on every card would
        // stop meaning anything, and absent is the overwhelming majority.
        const status = meta.status;
        if (status === 'archived' || status === 'dormant') {
            const badge = el('span', `agent-status agent-status-${status}`,
                             status === 'archived' ? 'Archived' : 'Not updated recently');
            badge.title = status === 'archived'
                ? 'The repository is archived on GitHub'
                : 'No commits in over a year';
            card.appendChild(badge);

            // A badge says stop; this says where to go. Rendered for
            // dormant entries too — the ten of them have been quiet for
            // eighteen to thirty months, and only entries with a badge reach
            // this branch at all, so a healthy project never shows one.
            // parseStack, not a hand-rolled split: models.py holds this as a
            // list and only the index metadata comma-joins it, so .split
            // would throw on an array and take the whole grid with it.
            const instead = parseStack(meta.alternatives)
                .map(name => String(name).trim()).filter(Boolean);
            if (instead.length) {
                const line = el('p', 'agent-alternatives');
                line.append('Try instead: ');
                instead.forEach((name, index) => {
                    if (index) line.append(', ');
                    const link = el('a', '', name);
                    link.href = `/agent/${encodeURIComponent(name)}`;
                    line.appendChild(link);
                });
                card.appendChild(line);
            }
        }

        if (typeof agent.score === 'number') {
            // A name match is not a similarity score. Showing it as "100%
            // match" would imply the embedding ranked it top, when in fact
            // the query was simply this agent's name.
            const byName = agent.match === 'name';
            const label = el('div', byName ? 'match-score match-name' : 'match-score',
                             byName ? 'name match' : `${Math.round(agent.score * 100)}% match`);
            label.title = byName
                ? 'Your query is this agent\u2019s name'
                : 'Semantic relevance to your query';
            card.appendChild(label);
        }

        const description = meta.description || agent.description || 'No description available.';
        card.appendChild(el('div', 'agent-description', description));

        const stack = el('div', 'tech-stack');
        parseStack(meta.stack)
            .map(tech => String(tech).trim())
            .filter(Boolean)
            .forEach(tech => {
                // Links now that /tech/<name> exists: "what else is built on
                // this" is the question a stack chip invites.
                const chip = el('a', 'tech-item', tech);
                chip.href = `/tech/${encodeURIComponent(tech)}`;
                stack.appendChild(chip);
            });
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
     * A control for filing this agent into a collection.
     *
     * Rendered only when the Collections module is loaded, so pages that do
     * not include it (the dashboard) are unaffected.
     */
    function saveControl(agent) {
        if (typeof Collections === 'undefined') return null;

        const name = (agent.metadata || {}).name || agent.name;
        if (!name) return null;

        const wrapper = el('span', 'save-control');
        const select = document.createElement('select');
        select.className = 'save-select';
        select.setAttribute('aria-label', `Add ${name} to a collection`);

        function refresh() {
            const holding = new Set(Collections.containing(name));
            const options = [el('option', null, 'Save to…')];
            options[0].value = '';

            Collections.names().forEach(collection => {
                const option = el('option', null,
                    holding.has(collection) ? `${collection} ✓` : collection);
                option.value = collection;
                option.disabled = holding.has(collection);
                options.push(option);
            });

            const create = el('option', null, '+ New collection…');
            create.value = '__new__';
            options.push(create);

            select.replaceChildren(...options);
        }

        select.addEventListener('change', () => {
            const choice = select.value;
            select.value = '';
            if (!choice) return;

            let target = choice;
            if (choice === '__new__') {
                const entered = window.prompt('Name the new collection:');
                if (!entered) return;
                const created = Collections.create(entered);
                if (!created.ok) {
                    window.alert(created.reason);
                    return;
                }
                target = created.name;
            }

            const result = Collections.add(target, name);
            if (!result.ok) window.alert(result.reason);
            refresh();
        });

        refresh();
        wrapper.appendChild(select);
        return wrapper;
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
            const footer = card.querySelector('.card-footer');
            if (footer) {
                const compare = compareLink(agent, agents);
                if (compare) footer.insertBefore(compare, footer.lastChild);

                const save = saveControl(agent);
                if (save) footer.insertBefore(save, footer.lastChild);
            }
            grid.appendChild(card);
        });
        container.replaceChildren(grid);
        return grid;
    }

    return { create, renderGrid, compareLink, saveControl, formatStars, parseStack, safeUrl };
})();
