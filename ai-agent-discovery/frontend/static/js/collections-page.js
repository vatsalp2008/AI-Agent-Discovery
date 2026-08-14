document.addEventListener('DOMContentLoaded', () => {
    const area = document.getElementById('collectionsArea');
    const form = document.getElementById('newCollectionForm');
    const nameInput = document.getElementById('newCollectionName');
    const result = document.getElementById('collectionsResult');
    const exportBtn = document.getElementById('exportCollections');
    const importInput = document.getElementById('importCollections');

    const say = UI.reporter(result);
    const showError = (message) => say(message, true);
    const showStatus = (message) => say(message);

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

    /** A filename-safe form of a collection name. */
    function slugify(name) {
        return name.toLowerCase().replace(/[^a-z0-9]+/g, '-')
            .replace(/^-+|-+$/g, '').slice(0, 40) || 'collection';
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

        const exportOne = document.createElement('button');
        exportOne.type = 'button';
        // Styled like the delete control beside it but deliberately not one:
        // a selector meaning "the delete button" must not match this.
        exportOne.className = 'collection-export';
        exportOne.textContent = 'Export';
        exportOne.setAttribute('aria-label', `Export the ${name} collection`);
        exportOne.addEventListener('click', () => {
            const payload = Collections.exportOne(name);
            if (!payload) {
                showError(`Could not export ${name}.`);
                return;
            }
            try {
                UI.download(payload, `collection-${slugify(name)}.json`);
                showStatus(`Exported ${name}.`);
            } catch (error) {
                console.error(error);
                showError('Could not export.');
            }
        });
        header.appendChild(exportOne);

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

    if (exportBtn) {
        exportBtn.addEventListener('click', () => {
            if (Collections.names().length === 0) {
                showError('There is nothing to export yet.');
                return;
            }
            try {
                UI.download(Collections.exportAll(), 'agent-collections.json');
                showStatus('Exported.');
            } catch (error) {
                console.error(error);
                showError('Could not export.');
            }
        });
    }

    if (importInput) {
        importInput.addEventListener('change', () => {
            UI.readFile(importInput, text => {
                const result = Collections.importAll(text);
                if (!result.ok) {
                    showError(result.reason);
                } else if (result.added === 0 && result.merged === 0) {
                    showStatus('Nothing new to import.');
                } else {
                    showStatus(`Imported: ${result.added} new, ${result.merged} merged.`);
                }
                render();
            }, () => showError('Could not read that file.'));
        });
    }

    render();
});
