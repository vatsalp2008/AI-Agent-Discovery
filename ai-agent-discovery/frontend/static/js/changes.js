/**
 * The catalogue's history.
 *
 * A curated directory is only trustworthy if you can see how it was curated.
 * This is the audit trail: what arrived, what left, and what was corrected.
 */
document.addEventListener('DOMContentLoaded', async () => {
    const area = document.getElementById('changesArea');

    /** A list of agent names, each linking to its page. */
    function nameList(names, className, label) {
        const item = document.createElement('li');
        item.className = className;

        item.append(`${label}: `);
        names.forEach((name, index) => {
            if (index) item.append(', ');
            const link = document.createElement('a');
            link.href = `/agent/${encodeURIComponent(name)}`;
            link.textContent = name;
            item.appendChild(link);
        });
        return item;
    }

    /** "description, category" rather than a wall of before-and-after text. */
    function editSummary(edited) {
        const item = document.createElement('li');
        item.className = 'change-edited';

        const fields = [...new Set(edited.flatMap(e => e.fields.map(f => f.field)))];
        const who = edited.length === 1 ? edited[0].name : `${edited.length} agents`;
        item.textContent = `Edited ${who} (${fields.join(', ')})`;
        return item;
    }

    function entryCard(entry) {
        const article = document.createElement('article');
        article.className = 'change-entry';

        const heading = document.createElement('h2');
        heading.textContent = entry.subject;
        article.appendChild(heading);

        const meta = document.createElement('p');
        meta.className = 'change-meta';
        const when = new Date(entry.at);
        meta.textContent = `${Number.isNaN(when.getTime()) ? entry.at : when.toLocaleDateString()}`
            + ` · ${entry.total} agents in the catalogue`;
        article.appendChild(meta);

        const list = document.createElement('ul');
        list.className = 'change-list';
        if (entry.added.length) list.appendChild(nameList(entry.added, 'change-added', 'Added'));
        if (entry.removed.length) {
            list.appendChild(nameList(entry.removed, 'change-removed', 'Removed'));
        }
        if (entry.edited.length) list.appendChild(editSummary(entry.edited));
        article.appendChild(list);

        return article;
    }

    try {
        const response = await fetch('/api/changelog?limit=100');
        if (!response.ok) throw new Error(`Request failed (${response.status})`);

        const body = await response.json();
        const entries = Array.isArray(body.entries) ? body.entries : [];

        if (!entries.length) {
            UI.showMessage(area, 'No history yet. Run changelog.py to build it from git.');
            return;
        }
        area.replaceChildren(...entries.map(entryCard));
        area.setAttribute('aria-busy', 'false');
    } catch (error) {
        console.error(error);
        UI.showError(area, 'Could not load the change history.');
    }
});
