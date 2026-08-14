/**
 * Side-by-side agent comparison.
 *
 * The chosen agents live in the URL (?names=A,B) so a comparison can be
 * shared and survives the Back button, the same way a search does.
 */
document.addEventListener('DOMContentLoaded', () => {
    const area = document.getElementById('compareArea');
    const picker = document.getElementById('comparePick');
    const clearButton = document.getElementById('compareClear');

    // Mirrors COMPARE_MAX_AGENTS. Without it the picker happily builds a
    // selection the API then refuses, so the limit arrives as a failed
    // request rather than as a control that stops.
    const MAX_COMPARE = 8;

    const ROWS = [
        { label: 'Category', get: m => m.category || 'Uncategorized' },
        { label: 'GitHub stars', get: m => AgentCard.formatStars(m.stars) },
        { label: 'Tech stack', get: m => AgentCard.parseStack(m.stack).join(', ') || '—' },
        { label: 'Description', get: m => m.description || '—' },
    ];

    function selected() {
        const raw = new URLSearchParams(window.location.search).get('names') || '';
        return raw.split(',').map(n => n.trim()).filter(Boolean);
    }

    function setSelected(names) {
        const url = names.length
            ? `${window.location.pathname}?names=${encodeURIComponent(names.join(','))}`
            : window.location.pathname;
        window.history.pushState({ names }, '', url);
        render();
    }

    function message(text) {
        UI.showMessage(area, text);
    }

    /**
     * Wrap the table so it can scroll sideways past a few agents.
     *
     * A region that scrolls must be reachable by keyboard, so it takes
     * `tabindex="0"` and a name — otherwise someone who cannot drag a
     * scrollbar cannot see the later columns at all. Only applied when there
     * is something to scroll to, since a focus stop that does nothing is its
     * own nuisance.
     */
    function scrollable(table, count) {
        if (count <= 3) return table;

        const wrapper = document.createElement('div');
        wrapper.className = 'compare-scroll';
        wrapper.setAttribute('role', 'region');
        wrapper.setAttribute('aria-label', `Comparison of ${count} agents, scrollable`);
        wrapper.tabIndex = 0;
        wrapper.appendChild(table);
        return wrapper;
    }

    /** One column per agent, one row per attribute. */
    function buildTable(agents) {
        const table = document.createElement('table');
        table.className = 'compare-table';

        const head = document.createElement('thead');
        const headRow = document.createElement('tr');
        headRow.appendChild(document.createElement('th'));
        agents.forEach(agent => {
            const th = document.createElement('th');
            th.scope = 'col';

            const link = document.createElement('a');
            link.href = `/agent/${encodeURIComponent(agent.name)}`;
            link.textContent = agent.name;
            th.appendChild(link);

            const remove = document.createElement('button');
            remove.type = 'button';
            remove.className = 'compare-remove';
            remove.textContent = '×';
            remove.setAttribute('aria-label', `Remove ${agent.name}`);
            remove.addEventListener('click', () => {
                setSelected(selected().filter(n => n.toLowerCase() !== agent.name.toLowerCase()));
            });
            th.appendChild(remove);

            headRow.appendChild(th);
        });
        head.appendChild(headRow);
        table.appendChild(head);

        const body = document.createElement('tbody');
        ROWS.forEach(row => {
            const tr = document.createElement('tr');
            const th = document.createElement('th');
            th.scope = 'row';
            th.textContent = row.label;
            tr.appendChild(th);

            agents.forEach(agent => {
                const td = document.createElement('td');
                td.textContent = row.get(agent.metadata || {});
                tr.appendChild(td);
            });
            body.appendChild(tr);
        });
        table.appendChild(body);
        return table;
    }

    async function render() {
        const names = selected();
        if (names.length === 0) {
            message('Pick two or more agents to compare.');
            return;
        }

        area.setAttribute('aria-busy', 'true');
        try {
            const response = await fetch(`/api/compare?names=${encodeURIComponent(names.join(','))}`);
            const data = await response.json();

            if (!response.ok) {
                message(data.error || 'Could not load the comparison.');
                return;
            }

            if ((data.agents || []).length === 0) {
                message('None of those agents were found.');
                return;
            }

            area.replaceChildren(scrollable(buildTable(data.agents), data.agents.length));

            const missing = (data.metadata || {}).missing || [];
            if (missing.length) {
                const note = document.createElement('p');
                note.className = 'result-notice';
                note.textContent = `Not found: ${missing.join(', ')}`;
                area.prepend(note);
            }
        } catch (error) {
            console.error(error);
            message('Could not load the comparison.');
        } finally {
            area.setAttribute('aria-busy', 'false');
        }
    }

    /**
     * Fill the picker, grouped by category.
     *
     * A flat list of a hundred-plus names is hard to scan; <optgroup> gives
     * the browser's own type-ahead something to work with and keeps related
     * agents together.
     */
    async function fillPicker() {
        if (!picker) return;
        try {
            // Paged: past AGENTS_MAX_PAGE_SIZE the server clamps and whole
            // late-alphabet categories would vanish from the picker.
            const { agents, failed } = await AgentsApi.fetchAll({ sort: 'category' });
            if (failed) {
                console.error('Could not load the full agent list for the picker.');
            }

            const byCategory = new Map();
            agents.forEach(agent => {
                const category = (agent.metadata || {}).category || 'Uncategorized';
                if (!byCategory.has(category)) byCategory.set(category, []);
                byCategory.get(category).push(agent.name);
            });

            [...byCategory.entries()]
                .sort((a, b) => a[0].localeCompare(b[0]))
                .forEach(([category, names]) => {
                    const group = document.createElement('optgroup');
                    group.label = `${category} (${names.length})`;
                    names.forEach(name => {
                        const option = document.createElement('option');
                        option.value = name;
                        option.textContent = name;
                        group.appendChild(option);
                    });
                    picker.appendChild(group);
                });
        } catch (error) {
            console.error('Could not load the agent list:', error);
        }
    }

    if (picker) {
        picker.addEventListener('change', () => {
            const name = picker.value;
            picker.value = '';
            if (!name) return;

            const current = selected();
            if (current.some(n => n.toLowerCase() === name.toLowerCase())) return;
            if (current.length >= MAX_COMPARE) {
                UI.showMessage(area, `You can compare up to ${MAX_COMPARE} agents at once. `
                    + 'Remove one to add another.', { error: true });
                return;
            }
            setSelected([...current, name]);
        });
    }

    if (clearButton) clearButton.addEventListener('click', () => setSelected([]));
    window.addEventListener('popstate', render);

    fillPicker();
    render();
});
