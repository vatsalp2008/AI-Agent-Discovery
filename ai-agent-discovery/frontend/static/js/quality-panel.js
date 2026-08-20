/**
 * How findable the catalogue is, on the page that already explains how it
 * changed.
 *
 * The score is a mean reciprocal rank per category: every agent is looked up
 * using its own use case, and the score says how near the top it comes back.
 * A directory that has grown past the point of being searchable should say so
 * where people can see it, rather than in a maintainer's terminal.
 *
 * Loaded independently of the change history on the same page. Either can
 * fail without taking the other with it, which matters because this one
 * depends on a file that is only written when somebody runs `make
 * quality-record` — the history is the reason to visit, and it should not
 * disappear because nobody has measured lately.
 */
document.addEventListener('DOMContentLoaded', async () => {
    const area = document.getElementById('qualityArea');
    if (!area) return;

    function scoreRow(category, score) {
        const row = document.createElement('li');
        row.className = 'quality-row';

        const name = document.createElement('span');
        name.className = 'quality-name';
        name.textContent = category;

        // A bar as well as the number: fourteen values between 0.9 and 1.0
        // are hard to rank by reading, and the shape is the point.
        const track = document.createElement('span');
        track.className = 'quality-track';
        const fill = document.createElement('span');
        fill.className = 'quality-fill';
        fill.style.width = `${Math.max(0, Math.min(1, score)) * 100}%`;
        track.appendChild(fill);

        const value = document.createElement('span');
        value.className = 'quality-value';
        value.textContent = score.toFixed(3);

        row.append(name, track, value);
        return row;
    }

    function movedList(moved) {
        const list = document.createElement('ul');
        list.className = 'quality-moved';
        moved.forEach(move => {
            const item = document.createElement('li');
            item.className = move.delta < 0 ? 'quality-fell' : 'quality-rose';
            item.textContent = `${move.category} ${move.delta > 0 ? '+' : ''}`
                + `${move.delta.toFixed(3)} (${move.from.toFixed(3)} → ${move.to.toFixed(3)})`;
            list.appendChild(item);
        });
        return list;
    }

    function render(body) {
        const latest = body.latest;
        const categories = Object.entries(latest.categories || {})
            .filter(([, score]) => Number.isFinite(score))
            .sort((a, b) => a[1] - b[1]);

        if (!categories.length) {
            UI.showMessage(area, 'No scores recorded yet.');
            return;
        }

        const heading = document.createElement('h2');
        heading.textContent = 'How findable it is';

        const summary = document.createElement('p');
        summary.className = 'quality-summary';
        const [worst, worstScore] = categories[0];
        summary.textContent =
            `Every agent is searched for using its own description. Across `
            + `${latest.agents} agents, the weakest category is ${worst} at `
            + `${worstScore.toFixed(3)} — 1.000 means every agent in it comes `
            + `back first.`;

        const list = document.createElement('ul');
        list.className = 'quality-scores';
        categories.forEach(([category, score]) => list.appendChild(scoreRow(category, score)));

        const parts = [heading, summary, list];

        if (Array.isArray(body.moved) && body.moved.length) {
            const movedHeading = document.createElement('h3');
            movedHeading.textContent = 'Since the previous measurement';
            parts.push(movedHeading, movedList(body.moved));
        }

        area.replaceChildren(...parts);
        area.setAttribute('aria-busy', 'false');
    }

    try {
        const response = await fetch('/api/quality');
        if (!response.ok) throw new Error(`Request failed (${response.status})`);

        const body = await response.json();
        if (!body || !body.latest) {
            // Not an error: nobody has run the measurement yet, and the
            // history below is still worth reading.
            area.replaceChildren();
            area.setAttribute('aria-busy', 'false');
            return;
        }
        render(body);
    } catch (error) {
        console.error(error);
        UI.showError(area, 'Could not load the quality scores.');
    }
});
