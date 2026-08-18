/**
 * Every technology in the catalogue, as a way in.
 *
 * /tech/<name> answers "what else is built on this", but nothing listed the
 * technologies themselves — you had to already know one to get there. At 113
 * of them, two thirds used by a single agent, a flat list is a wall: the
 * filter box is what makes it navigable.
 */
document.addEventListener('DOMContentLoaded', async () => {
    const area = document.getElementById('techIndex');
    const countEl = document.getElementById('techIndexCount');
    const filter = document.getElementById('techFilter');

    let technologies = [];

    function chip(tech) {
        const link = document.createElement('a');
        link.className = 'filter-tag';
        link.href = `/tech/${encodeURIComponent(tech.name)}`;
        link.textContent = `${tech.name} (${tech.count})`;
        return link;
    }

    /**
     * Two groups, because they answer different questions: the technologies
     * several agents share are worth browsing, and the long tail is worth
     * searching. Sorting the whole lot together buries the first in the
     * second.
     */
    function render(needle = '') {
        const matching = technologies.filter(
            t => t.name.toLowerCase().includes(needle.toLowerCase()));

        if (!matching.length) {
            // UI.showMessage clears aria-busy itself, so this path needs
            // nothing extra — the tests below hold it to that.
            UI.showMessage(area, needle
                ? `Nothing matches “${needle}”.`
                : 'No technologies recorded yet.');
            return;
        }

        const shared = matching.filter(t => t.count > 1);
        const once = matching.filter(t => t.count === 1);

        const sections = [];
        if (shared.length) sections.push(group('Used by several agents', shared));
        if (once.length) sections.push(group('Used by one agent', once));

        area.replaceChildren(...sections);
        area.setAttribute('aria-busy', 'false');
    }

    function group(title, items) {
        const section = document.createElement('section');
        section.className = 'tech-group';

        const heading = document.createElement('h2');
        heading.textContent = `${title} (${items.length})`;
        section.appendChild(heading);

        const list = document.createElement('div');
        list.className = 'filters';
        items.forEach(t => list.appendChild(chip(t)));
        section.appendChild(list);

        return section;
    }

    try {
        const response = await fetch('/api/tech');
        if (!response.ok) throw new Error(`Request failed (${response.status})`);

        const body = await response.json();
        technologies = Array.isArray(body) ? body : [];

        countEl.textContent = `${technologies.length} technologies across the catalogue`;
        render();
    } catch (error) {
        console.error(error);
        UI.showError(area, 'Could not load the technologies.');
        countEl.textContent = 'Could not load.';
        return;
    }

    if (filter) {
        filter.addEventListener('input', () => render(filter.value.trim()));
    }
});
