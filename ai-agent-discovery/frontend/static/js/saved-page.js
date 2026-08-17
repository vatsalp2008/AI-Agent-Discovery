/**
 * The saved searches page: list them, re-run them, show what moved.
 *
 * Checking runs the searches one at a time rather than in parallel. /api/search
 * is rate limited, and twenty saved searches fired at once is exactly the
 * burst the limiter exists to refuse — the page would then report failures
 * that are entirely its own fault.
 */
document.addEventListener('DOMContentLoaded', () => {
    const area = document.getElementById('savedArea');
    const result = document.getElementById('savedResult');
    const checkAll = document.getElementById('checkAll');
    const clearButton = document.getElementById('clearSaved');
    const exportButton = document.getElementById('exportSaved');
    const importInput = document.getElementById('importSaved');

    const say = UI.reporter(result);

    /**
     * Re-run one saved search. Throws so the caller can report which failed.
     *
     * POST, not GET: /api/search takes its query in a JSON body. A GET is a
     * 405, which is how this shipped once — the tests stubbed fetch by URL
     * and never looked at the method.
     *
     * No `summarize`: a check wants the result set, and a generation per
     * saved search would be slow and would burn the tighter summary budget.
     */
    async function rerun(entry) {
        const payload = { query: entry.query };
        if (entry.category) payload.category = entry.category;
        // The snapshot was taken with this applied; re-running without it
        // would report every excluded project as brand new.
        if (entry.maintained) payload.maintained = true;

        const response = await fetch('/api/search', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        if (!response.ok) {
            throw new Error(response.status === 429
                ? 'Too many searches at once; try again shortly.'
                : `Search failed (${response.status})`);
        }
        const body = await response.json();
        return Array.isArray(body.results) ? body.results : [];
    }

    function changeList(changes) {
        const list = document.createElement('ul');
        list.className = 'change-list';

        changes.added.forEach(name => {
            const item = document.createElement('li');
            item.className = 'change-added';
            item.textContent = `New: ${name}`;
            list.appendChild(item);
        });
        changes.removed.forEach(name => {
            const item = document.createElement('li');
            item.className = 'change-removed';
            item.textContent = `No longer matches: ${name}`;
            list.appendChild(item);
        });
        changes.moved.forEach(({ name, from, to }) => {
            const item = document.createElement('li');
            item.className = to > from ? 'change-up' : 'change-down';
            const arrow = to > from ? '↑' : '↓';
            item.textContent = `${name}: ${from.toLocaleString()} ${arrow} ${to.toLocaleString()} stars`;
            list.appendChild(item);
        });
        return list;
    }

    function card(entry) {
        const article = document.createElement('article');
        article.className = 'saved-card';
        article.dataset.query = entry.query;
        article.dataset.category = entry.category || '';
        article.dataset.maintained = entry.maintained ? '1' : '';

        const heading = document.createElement('h2');
        const link = document.createElement('a');
        const params = new URLSearchParams({ q: entry.query });
        if (entry.category) params.set('category', entry.category);
        link.href = `/?${params}`;
        link.textContent = entry.query;
        heading.appendChild(link);
        article.appendChild(heading);

        const meta = document.createElement('p');
        meta.className = 'saved-meta';
        const bits = [`${entry.snapshot.names.length} result(s) when saved`];
        if (entry.category) bits.push(`filtered to ${entry.category}`);
        if (entry.maintained) bits.push('maintained only');
        if (entry.snapshot.at) {
            bits.push(`saved ${new Date(entry.snapshot.at).toLocaleDateString()}`);
        }
        meta.textContent = bits.join(' · ');
        article.appendChild(meta);

        const changes = document.createElement('div');
        changes.className = 'saved-changes';
        article.appendChild(changes);

        const actions = document.createElement('div');
        actions.className = 'saved-actions';

        const check = document.createElement('button');
        check.type = 'button';
        check.className = 'control-button';
        check.textContent = 'Check';
        check.setAttribute('aria-label', `Check ${entry.query} for changes`);
        check.addEventListener('click', () => checkOne(entry, article));
        actions.appendChild(check);

        const remove = document.createElement('button');
        remove.type = 'button';
        remove.className = 'control-button';
        remove.textContent = 'Remove';
        remove.setAttribute('aria-label', `Remove ${entry.query}`);
        remove.addEventListener('click', () => {
            SavedSearches.remove(entry.query, entry.category,
                                 { maintained: entry.maintained });
            render();
            say(`Removed “${entry.query}”.`);
        });
        actions.appendChild(remove);

        article.appendChild(actions);
        return article;
    }

    /** Show one search's changes, and adopt the new results as the baseline. */
    function showChanges(entry, article, changes) {
        const container = article.querySelector('.saved-changes');

        if (!changes.comparable) {
            UI.showMessage(container, 'Saved before results were recorded; '
                + 'this check becomes the baseline.');
            return;
        }
        if (SavedSearches.isEmpty(changes)) {
            UI.showMessage(container, 'No change since you saved it.');
            return;
        }
        container.replaceChildren(changeList(changes));
    }

    /** The saved entry as it stands now, not as it was when rendered. */
    function current(entry) {
        return SavedSearches.list().find(e => sameSearch(e, entry)) || entry;
    }

    /** Two records describe the same saved search. */
    function sameSearch(a, b) {
        return a.query === b.query
            && (a.category || '') === (b.category || '')
            && Boolean(a.maintained) === Boolean(b.maintained);
    }

    async function checkOne(entry, article) {
        const container = article.querySelector('.saved-changes');
        UI.showMessage(container, 'Checking…');

        try {
            const fresh = await rerun(entry);
            // Re-read rather than using the captured snapshot: a previous
            // check already replaced it, and diffing against the original
            // save would report the same change every time.
            const changes = SavedSearches.diff(current(entry).snapshot, fresh);
            showChanges(entry, article, changes);
            // Adopt the new results, so checking twice does not report the
            // same change twice.
            SavedSearches.refresh(entry.query, entry.category, fresh,
                                  { maintained: entry.maintained });
            return changes;
        } catch (error) {
            UI.showError(container, error.message);
            return null;
        }
    }

    async function checkEveryone() {
        const cards = [...area.querySelectorAll('.saved-card')];
        if (!cards.length) return;

        checkAll.disabled = true;
        checkAll.textContent = 'Checking…';
        UI.setBusy(true, area);

        let changed = 0;
        let failed = 0;
        // Sequential on purpose; see the note at the top of this file.
        for (const article of cards) {
            const entry = SavedSearches.list().find(e => sameSearch(e, {
                query: article.dataset.query,
                category: article.dataset.category,
                maintained: article.dataset.maintained === '1',
            }));
            if (!entry) continue;

            const changes = await checkOne(entry, article);
            if (changes === null) failed += 1;
            else if (changes.comparable && !SavedSearches.isEmpty(changes)) changed += 1;
        }

        UI.setBusy(false, area);
        checkAll.disabled = false;
        checkAll.textContent = 'Check for changes';

        if (failed === cards.length) {
            say('Could not check any of them.', true);
        } else if (failed) {
            say(`${changed} changed; ${failed} could not be checked.`, true);
        } else {
            say(changed ? `${changed} of ${cards.length} changed.` : 'Nothing has changed.');
        }
    }

    function render() {
        const entries = SavedSearches.list();

        if (!entries.length) {
            UI.showMessage(area, 'No saved searches yet. Run a search and choose '
                + '“Save this search” to watch it for changes.');
            checkAll.disabled = true;
            clearButton.disabled = true;
            return;
        }

        checkAll.disabled = false;
        clearButton.disabled = false;
        area.replaceChildren(...entries.map(card));
    }

    if (exportButton) {
        exportButton.addEventListener('click', () => {
            if (!SavedSearches.list().length) {
                say('There is nothing to export yet.', true);
                return;
            }
            try {
                UI.download(SavedSearches.exportAll(), 'saved-searches.json');
                say('Exported.');
            } catch (error) {
                console.error(error);
                say('Could not export.', true);
            }
        });
    }

    if (importInput) {
        importInput.addEventListener('change', () => {
            UI.readFile(importInput, text => {
                const outcome = SavedSearches.importAll(text);
                if (!outcome.ok) {
                    say(outcome.reason, true);
                } else if (outcome.full) {
                    // Discarding searches is not "nothing new"; say so, and
                    // say it as a problem.
                    say(`Imported ${outcome.added}. ${outcome.full} could not fit — `
                        + `remove some to get below ${SavedSearches.MAX_SAVED}.`, true);
                } else if (!outcome.added) {
                    say('Nothing new to import; you already have them all.');
                } else {
                    say(`Imported ${outcome.added}; skipped ${outcome.skipped} already saved.`);
                }
                render();
            }, () => say('Could not read that file.', true));
        });
    }

    checkAll.addEventListener('click', checkEveryone);
    clearButton.addEventListener('click', () => {
        if (!SavedSearches.list().length) return;
        SavedSearches.clear();
        render();
        say('Removed every saved search.');
    });

    render();

    // Exposed for the tests, which drive the page rather than the module.
    window.SavedPage = { render, checkOne };
});
