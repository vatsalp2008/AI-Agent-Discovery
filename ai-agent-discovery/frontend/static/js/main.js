document.addEventListener('DOMContentLoaded', () => {
    const searchForm = document.getElementById('searchForm');
    const searchInput = document.getElementById('searchInput');
    const resultsArea = document.getElementById('resultsArea');
    const filters = document.getElementById('filters');
    const suggestionList = document.getElementById('suggestions');
    const recent = document.getElementById('recent');
    const recentList = document.getElementById('recentList');
    const recentClear = document.getElementById('recentClear');

    // Category chips act as a real server-side filter, not just a canned query.
    let activeCategory = null;
    // Reused by the no-match notice, which suggests somewhere to go instead.
    let loadedCategories = [];

    // Guards against a slow summary landing after a newer search started.
    let searchToken = 0;

    /**
     * The query and category live in the URL so a search can be bookmarked,
     * shared, and walked back through with the browser's Back button.
     */
    function readStateFromUrl() {
        return SearchState.fromSearch(window.location.search);
    }

    function writeStateToUrl(query, category, { replace = false } = {}) {
        const url = SearchState.toUrl(window.location.pathname, { query, category });
        if (url === window.location.pathname + window.location.search) return;

        const state = { query, category };
        if (replace) {
            window.history.replaceState(state, '', url);
        } else {
            window.history.pushState(state, '', url);
        }
    }

    function showMessage(text, isError) {
        UI.showMessage(resultsArea, text, { error: isError });
    }

    /**
     * Show a failure with a way out. A transient error (Ollama still loading a
     * model, a dropped connection) usually succeeds on a second attempt, so
     * make retrying one click rather than a retype.
     */
    function showRetryableError(text, retry) {
        const wrapper = document.createElement('div');
        wrapper.className = 'result-error';

        const message = document.createElement('p');
        message.className = 'result-message error';
        message.textContent = text;
        wrapper.appendChild(message);

        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'retry-btn';
        button.textContent = 'Try again';
        button.addEventListener('click', () => {
            button.disabled = true;
            button.textContent = 'Retrying…';
            retry();
        });
        wrapper.appendChild(button);

        resultsArea.replaceChildren(wrapper);
        button.focus();
    }

    /**
     * The model-written overview. Labelled as generated so it is not mistaken
     * for catalogue data, and inserted as text so the model cannot emit markup.
     */
    function makeSummary(text, { pending = false } = {}) {
        const box = document.createElement('aside');
        box.className = pending ? 'summary pending' : 'summary';

        const label = document.createElement('span');
        label.className = 'summary-label';
        label.textContent = 'AI overview';
        box.appendChild(label);

        const body = document.createElement('p');
        body.textContent = text;
        box.appendChild(body);

        return box;
    }

    /**
     * Copy the current search URL. Uses the async clipboard API where it is
     * available (it needs a secure context), and falls back to selecting a
     * temporary input so the button still does something over plain HTTP.
     */
    async function copyCurrentUrl() {
        const url = window.location.href;
        if (navigator.clipboard && window.isSecureContext) {
            await navigator.clipboard.writeText(url);
            return;
        }

        const scratch = document.createElement('input');
        scratch.value = url;
        scratch.setAttribute('readonly', '');
        scratch.style.position = 'absolute';
        scratch.style.left = '-9999px';
        document.body.appendChild(scratch);
        scratch.select();
        try {
            document.execCommand('copy');
        } finally {
            scratch.remove();
        }
    }

    function makeCopyLinkButton() {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'copy-link';
        button.textContent = 'Copy link';

        button.addEventListener('click', async () => {
            try {
                await copyCurrentUrl();
                button.textContent = 'Copied';
            } catch (error) {
                console.error('Could not copy the link:', error);
                button.textContent = 'Press Ctrl+C';
            }
            // Announce the outcome, then settle back to the resting label.
            button.setAttribute('aria-live', 'polite');
            setTimeout(() => { button.textContent = 'Copy link'; }, 2000);
        });
        return button;
    }

    /** Redraw the recent-query chips. Hidden entirely when there are none. */
    function renderRecent() {
        if (!recent || !recentList) return;

        const entries = RecentSearches.read();
        recent.hidden = entries.length === 0;
        recentList.replaceChildren();

        entries.forEach(entry => {
            const chip = document.createElement('button');
            chip.type = 'button';
            chip.className = 'recent-item';
            chip.textContent = RecentSearches.label(entry);
            chip.addEventListener('click', () => {
                searchInput.value = entry.query;
                setActiveChip(entry.category || null);
                performSearch(entry.query);
            });
            recentList.appendChild(chip);
        });
    }

    function makeExportButton(format, run) {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'export-btn';
        button.textContent = `Export ${format}`;
        button.addEventListener('click', () => {
            try {
                run();
            } catch (error) {
                console.error(`Could not export ${format}:`, error);
                button.textContent = 'Export failed';
                setTimeout(() => { button.textContent = `Export ${format}`; }, 2000);
            }
        });
        return button;
    }

    /**
     * A notice offering categories to browse instead.
     *
     * "Nothing matched" is honest but a dead end. With a catalogue this size
     * the useful next step is usually a category, so offer the largest few
     * rather than leaving the user to guess what is in here.
     */
    function makeNoMatchNotice(text) {
        const notice = makeNotice(text);

        const categories = loadedCategories.slice(0, 4);
        if (categories.length === 0) return notice;

        const suggestion = document.createElement('span');
        suggestion.className = 'notice-suggestion';
        suggestion.append(' Try browsing ');

        categories.forEach((category, index) => {
            if (index) suggestion.append(index === categories.length - 1 ? ' or ' : ', ');
            const link = document.createElement('a');
            link.href = `/category/${encodeURIComponent(category.name)}`;
            link.textContent = category.name;
            suggestion.appendChild(link);
        });
        suggestion.append('.');

        notice.appendChild(suggestion);
        return notice;
    }

    function makeNotice(text) {
        const notice = document.createElement('p');
        notice.className = 'result-notice';
        notice.textContent = text;
        return notice;
    }

    function showLoading() {
        const wrapper = document.createElement('div');
        wrapper.className = 'loading';
        wrapper.appendChild(Object.assign(document.createElement('div'), { className: 'spinner' }));
        const label = document.createElement('p');
        label.textContent = 'Searching the agentverse...';
        wrapper.appendChild(label);
        resultsArea.replaceChildren(wrapper);
    }

    /**
     * Ask for the model-written overview separately, once results are already
     * on screen. Generation on a local model can take seconds, and there is no
     * reason to make the user wait for it to see their results; the server
     * caches the retrieval half, so the second call only pays for generation.
     */
    async function requestSummary(query, token) {
        const placeholder = makeSummary('Generating overview…', { pending: true });
        resultsArea.prepend(placeholder);

        const body = SearchState.searchBody({ query, category: activeCategory, summarize: true });

        try {
            const response = await fetch('/api/search', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
            });
            const data = await response.json();

            // A newer search has started; this result is stale.
            if (token !== searchToken) return;

            if (response.ok && data.summary) {
                placeholder.replaceWith(makeSummary(data.summary));
            } else {
                placeholder.remove();
            }
        } catch (error) {
            console.error('Could not generate overview:', error);
            if (token === searchToken) placeholder.remove();
        }
    }

    async function performSearch(query, { updateUrl = true } = {}) {
        if (!query.trim()) return;

        const token = ++searchToken;
        if (updateUrl) {
            writeStateToUrl(query.trim(), activeCategory);
            // Only record searches the user actually initiated, not those
            // replayed from the URL or the Back button.
            RecentSearches.add(query, activeCategory);
            renderRecent();
        }

        showLoading();
        resultsArea.setAttribute('aria-busy', 'true');

        const body = SearchState.searchBody({ query, category: activeCategory });

        try {
            const response = await fetch('/api/search', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(body)
            });

            const data = await response.json();

            if (!response.ok) {
                // A 4xx is the client's fault and retrying changes nothing;
                // a 5xx is worth another attempt.
                if (response.status >= 500) {
                    showRetryableError(data.error || 'Search failed.', () => performSearch(query, { updateUrl: false }));
                } else {
                    showMessage(data.error || 'Search failed.', true);
                }
                return;
            }

            if (Array.isArray(data.results) && data.results.length > 0) {
                AgentCard.renderGrid(resultsArea, data.results);
                // Vector search always returns something. Say so plainly when
                // nothing actually matched well, rather than presenting weak
                // hits as if they were answers.
                // A results page is a shareable thing; offer the link.
                const bar = document.createElement('div');
                bar.className = 'results-bar';
                bar.appendChild(makeExportButton('CSV', () => ExportResults.asCsv(data.results, query)));
                bar.appendChild(makeExportButton('JSON', () => ExportResults.asJson(data.results, query)));
                bar.appendChild(makeCopyLinkButton());
                resultsArea.prepend(bar);

                if (data.metadata && data.metadata.confident === false) {
                    resultsArea.prepend(makeNoMatchNotice(
                        'Nothing matched your query well. Showing the closest agents anyway.'
                    ));
                } else {
                    requestSummary(query, token);
                }
            } else {
                showMessage(SearchState.emptyMessage(activeCategory));
            }
        } catch (error) {
            console.error('Error:', error);
            showRetryableError(
                'Could not reach the server.',
                () => performSearch(query, { updateUrl: false })
            );
        } finally {
            resultsArea.setAttribute('aria-busy', 'false');
        }
    }

    /**
     * Category chips are real <button>s, not styled <span>s: they need to be
     * reachable by keyboard and expose their pressed state to assistive tech.
     */
    function setActiveChip(name) {
        filters.querySelectorAll('.filter-tag').forEach(t => {
            const active = t.dataset.category === name;
            t.classList.toggle('active', active);
            t.setAttribute('aria-pressed', active ? 'true' : 'false');
        });
        activeCategory = name;
    }

    function makeChip(name, count) {
        const chip = document.createElement('button');
        chip.type = 'button';
        chip.className = 'filter-tag';
        chip.textContent = count === undefined ? name : `${name} (${count})`;
        chip.dataset.category = name;
        chip.setAttribute('aria-pressed', 'false');

        chip.addEventListener('click', () => {
            // Clicking the active chip clears the filter.
            const wasActive = chip.getAttribute('aria-pressed') === 'true';
            setActiveChip(wasActive ? null : name);

            if (searchInput.value.trim()) {
                performSearch(searchInput.value);
            } else {
                writeStateToUrl('', activeCategory);
            }
        });
        return chip;
    }

    async function loadCategories() {
        try {
            const response = await fetch('/api/categories');
            if (!response.ok) return;
            const categories = await response.json();
            if (!Array.isArray(categories) || categories.length === 0) return;
            loadedCategories = categories;
            categories.forEach(c => filters.appendChild(makeChip(c.name, c.count)));
            // Re-apply a category that arrived in the URL.
            if (activeCategory) setActiveChip(activeCategory);
        } catch (error) {
            console.error('Could not load categories:', error);
        }
    }

    /**
     * Fill the empty results area on first visit so the page is not blank
     * before the user has typed anything.
     */
    async function loadInitialAgents() {
        try {
            const response = await fetch('/api/agents?limit=6');
            if (!response.ok) return;

            const body = await response.json();
            const agents = body.agents || [];

            if (agents.length === 0) {
                showMessage('No agents indexed yet. Run seed.py to populate the vector store.');
                return;
            }

            const heading = document.createElement('h2');
            heading.className = 'results-heading';
            heading.textContent = body.metadata.has_more
                ? `Browsing ${agents.length} of ${body.metadata.total} agents`
                : 'Browse agents';

            AgentCard.renderGrid(resultsArea, agents);
            resultsArea.prepend(heading);
        } catch (error) {
            console.error('Could not load agents:', error);
        }
    }

    // --- Name suggestions -------------------------------------------------
    // A complement to semantic search, for when you half-remember a name.
    let suggestionNames = [];
    let suggestionItems = [];
    let activeSuggestion = -1;

    /** Every agent name, for the suggestion list. */
    async function loadSuggestionNames() {
        if (!suggestionList) return;
        const body = await AgentsApi.fetchAll({ sort: 'name' });
        suggestionNames = (body.agents || []).map(a => ({ name: a.name }));
    }

    function closeSuggestions() {
        if (!suggestionList) return;
        suggestionList.hidden = true;
        suggestionList.replaceChildren();
        suggestionItems = [];
        activeSuggestion = -1;
        searchInput.setAttribute('aria-expanded', 'false');
        searchInput.removeAttribute('aria-activedescendant');
    }

    function highlightSuggestion(index) {
        suggestionItems.forEach((item, i) => {
            const active = i === index;
            item.classList.toggle('active', active);
            item.setAttribute('aria-selected', active ? 'true' : 'false');
        });
        activeSuggestion = index;
        if (index >= 0) {
            searchInput.setAttribute('aria-activedescendant', suggestionItems[index].id);
        } else {
            searchInput.removeAttribute('aria-activedescendant');
        }
    }

    function chooseSuggestion(name) {
        searchInput.value = name;
        closeSuggestions();
        performSearch(name);
    }

    function showSuggestions() {
        if (!suggestionList) return;

        const matches = Suggest.rank(suggestionNames, searchInput.value);
        if (matches.length === 0) {
            closeSuggestions();
            return;
        }

        suggestionItems = matches.map((match, index) => {
            const item = document.createElement('li');
            item.className = 'suggestion';
            item.id = `suggestion-${index}`;
            item.setAttribute('role', 'option');
            item.setAttribute('aria-selected', 'false');

            Suggest.segments(match.name, searchInput.value).forEach(part => {
                const span = document.createElement(part.match ? 'mark' : 'span');
                span.textContent = part.text;
                item.appendChild(span);
            });

            // mousedown, not click: blur would close the list first.
            item.addEventListener('mousedown', (e) => {
                e.preventDefault();
                chooseSuggestion(match.name);
            });
            return item;
        });

        suggestionList.replaceChildren(...suggestionItems);
        suggestionList.hidden = false;
        searchInput.setAttribute('aria-expanded', 'true');
        highlightSuggestion(-1);
    }

    if (suggestionList) {
        searchInput.addEventListener('input', showSuggestions);
        searchInput.addEventListener('blur', () => setTimeout(closeSuggestions, 120));

        searchInput.addEventListener('keydown', (e) => {
            if (suggestionList.hidden) return;

            if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
                e.preventDefault();
                highlightSuggestion(
                    Suggest.nextIndex(activeSuggestion, suggestionItems.length,
                                      e.key === 'ArrowDown' ? 1 : -1));
            } else if (e.key === 'Enter' && activeSuggestion >= 0) {
                e.preventDefault();
                chooseSuggestion(suggestionItems[activeSuggestion].textContent);
            } else if (e.key === 'Escape') {
                closeSuggestions();
            }
        });
    }

    // Event Listeners. A submit handler covers the button, the Enter key and
    // the browser's own search-field affordances in one place.
    searchForm.addEventListener('submit', (e) => {
        e.preventDefault();
        closeSuggestions();
        performSearch(searchInput.value);
    });

    async function applyState(state, { updateUrl = false } = {}) {
        activeCategory = state.category;
        searchInput.value = state.query;
        setActiveChip(state.category);

        if (state.query) {
            await performSearch(state.query, { updateUrl });
        } else {
            await loadInitialAgents();
        }
    }

    window.addEventListener('popstate', (event) => {
        applyState(event.state || readStateFromUrl());
    });

    // Boot: honour whatever the URL already says. The chips may not exist yet,
    // so loadCategories re-applies the active one once they do.
    const initial = readStateFromUrl();
    activeCategory = initial.category;
    if (recentClear) {
        recentClear.addEventListener('click', () => {
            RecentSearches.clear();
            renderRecent();
        });
    }

    loadCategories();
    loadSuggestionNames();
    renderRecent();
    applyState(initial);
});
