document.addEventListener('DOMContentLoaded', () => {
    const area = document.getElementById('collectionsArea');
    const form = document.getElementById('newCollectionForm');
    const nameInput = document.getElementById('newCollectionName');
    const errorEl = document.getElementById('collectionsError');

    function showError(message) {
        if (!errorEl) return;
        errorEl.textContent = message || '';
        errorEl.hidden = !message;
    }

    function agentChip(collection, agent) {
        const chip = document.createElement('span');
        chip.className = 'collection-agent';

        const link = document.createElement('a');
        link.href = `/agent/${encodeURIComponent(agent)}`;
        link.textContent = agent;
        chip.appendChild(link);

        const remove = document.createElement('button');
        remove.type = 'button';
        remove.className = 'collection-remove';
        remove.textContent = '×';
        remove.setAttribute('aria-label', `Remove ${agent} from ${collection}`);
        remove.addEventListener('click', () => {
            Collections.remove(collection, agent);
            render();
        });
        chip.appendChild(remove);
        return chip;
    }

    function card(name) {
        const agents = Collections.agentsIn(name);
        const section = document.createElement('section');
        section.className = 'collection-card';

        const header = document.createElement('div');
        header.className = 'collection-header';

        const heading = document.createElement('h2');
        heading.textContent = `${name} (${agents.length})`;
        header.appendChild(heading);

        const compareUrl = Collections.compareUrl(name);
        if (compareUrl) {
            const compare = document.createElement('a');
            compare.className = 'compare-link';
            compare.href = compareUrl;
            compare.textContent = 'Compare';
            header.appendChild(compare);
        }

        const del = document.createElement('button');
        del.type = 'button';
        del.className = 'collection-delete';
        del.textContent = 'Delete';
        del.setAttribute('aria-label', `Delete the ${name} collection`);
        del.addEventListener('click', () => {
            Collections.destroy(name);
            render();
        });
        header.appendChild(del);
        section.appendChild(header);

        if (agents.length === 0) {
            const empty = document.createElement('p');
            empty.className = 'result-message';
            empty.textContent = 'Empty. Add agents from a search result.';
            section.appendChild(empty);
        } else {
            const list = document.createElement('div');
            list.className = 'collection-agents';
            agents.forEach(agent => list.appendChild(agentChip(name, agent)));
            section.appendChild(list);
        }
        return section;
    }

    function render() {
        const names = Collections.names();
        if (names.length === 0) {
            const p = document.createElement('p');
            p.className = 'result-message';
            p.textContent = 'No collections yet. Create one above, then add agents from a search.';
            area.replaceChildren(p);
            return;
        }
        area.replaceChildren(...names.map(card));
    }

    if (form) {
        form.addEventListener('submit', (e) => {
            e.preventDefault();
            const result = Collections.create(nameInput.value);
            showError(result.ok ? '' : result.reason);
            if (result.ok) {
                nameInput.value = '';
                render();
            }
        });
    }

    render();
});
