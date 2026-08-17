/**
 * Wiring tests for main.js: the parts that talk to the DOM and the API.
 * The pure helpers are covered in search-state.test.js.
 */

import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { SEARCH_HTML, bootPage, flush, scriptsFor, stubFetch } from './helpers.js';

const CATEGORIES = [
    { name: 'Code Generation', count: 6 },
    { name: 'Research', count: 4 },
];

function makeResult(name, score = 0.9) {
    return {
        name,
        description: `${name} description.`,
        score,
        metadata: { name, category: 'Code Generation', stack: 'Python', stars: 100, description: `${name} description.` },
    };
}

function defaultRoutes(overrides = {}) {
    return {
        '/api/categories': { body: CATEGORIES },
        '/api/agents': { body: { agents: [makeResult('Aider')], metadata: { total: 1, has_more: false } } },
        '/api/search': { body: { results: [makeResult('Cursor')], metadata: { confident: true } } },
        '/api/summary': { body: { summary: null } },
        ...overrides,
    };
}

async function boot(routes = defaultRoutes()) {
    const calls = stubFetch(routes);
    bootPage({
        html: SEARCH_HTML,
        script: 'main.js',
        extraScripts: scriptsFor('index.html', 'main.js'),
    });
    await flush();
    return calls;
}

function submitSearch(query) {
    document.getElementById('searchInput').value = query;
    document.getElementById('searchForm').dispatchEvent(
        new window.Event('submit', { bubbles: true, cancelable: true })
    );
}

beforeEach(() => {
    window.history.replaceState({}, '', '/');
    // The page keeps recent searches and saved searches in localStorage,
    // which jsdom shares across the whole file. Without this a test sees
    // whatever its predecessors left behind.
    localStorage.clear();
});

afterEach(() => {
    delete globalThis.fetch;
});

describe('first load', () => {
    it('renders category chips as real buttons', async () => {
        await boot();
        const chips = document.querySelectorAll('#filters .filter-tag');
        expect(chips).toHaveLength(2);
        expect(chips[0].tagName).toBe('BUTTON');
        expect(chips[0].getAttribute('aria-pressed')).toBe('false');
        expect(chips[0].textContent).toBe('Code Generation (6)');
    });

    it('previews agents so the page is not blank', async () => {
        await boot();
        expect(document.querySelectorAll('.agent-card').length).toBeGreaterThan(0);
    });

    it('tells the user to seed when the index is empty', async () => {
        await boot(defaultRoutes({
            '/api/agents': { body: { agents: [], metadata: { total: 0, has_more: false } } },
        }));
        expect(document.querySelector('#resultsArea').textContent).toContain('seed.py');
    });
});

describe('searching', () => {
    it('posts the query and renders the results', async () => {
        const calls = await boot();
        submitSearch('code editor');
        await flush();

        const search = calls.find(c => c.url.includes('/api/search'));
        expect(JSON.parse(search.options.body).query).toBe('code editor');
        expect(document.querySelector('.agent-name').textContent).toBe('Cursor');
    });

    it('does not search when the box is empty', async () => {
        const calls = await boot();
        const before = calls.length;
        submitSearch('   ');
        await flush();
        expect(calls.length).toBe(before);
    });

    it('clears aria-busy once results arrive', async () => {
        await boot();
        submitSearch('code editor');
        await flush();
        expect(document.getElementById('resultsArea').getAttribute('aria-busy')).toBe('false');
    });

    it('reports a server error instead of rendering nothing', async () => {
        await boot(defaultRoutes({
            '/api/search': { ok: false, status: 400, body: { error: 'query too long' } },
        }));
        submitSearch('x'.repeat(10));
        await flush();
        expect(document.querySelector('.result-message').textContent).toContain('query too long');
    });

    it('survives a network failure', async () => {
        await boot(defaultRoutes({ '/api/search': new Error('offline') }));
        submitSearch('anything');
        await flush();
        expect(document.querySelector('.result-message.error')).not.toBeNull();
        expect(document.getElementById('resultsArea').getAttribute('aria-busy')).toBe('false');
    });

    it('says so plainly when nothing matched well', async () => {
        await boot(defaultRoutes({
            '/api/search': { body: { results: [makeResult('Cursor', 0.3)], metadata: { confident: false } } },
        }));
        submitSearch('banana bread');
        await flush();
        expect(document.querySelector('.result-notice').textContent).toContain('Nothing matched');
    });

    it('reports an empty result set', async () => {
        await boot(defaultRoutes({
            '/api/search': { body: { results: [], metadata: { confident: false } } },
        }));
        submitSearch('nothing at all');
        await flush();
        expect(document.querySelector('#resultsArea').textContent).toContain('No agents found');
    });
});

describe('category chips', () => {
    it('sends the category with the query', async () => {
        const calls = await boot();
        document.querySelector('#filters .filter-tag').click();
        submitSearch('editor');
        await flush();

        const search = calls.filter(c => c.url.includes('/api/search')).pop();
        expect(JSON.parse(search.options.body).category).toBe('Code Generation');
    });

    it('marks the active chip for assistive tech', async () => {
        await boot();
        const chip = document.querySelector('#filters .filter-tag');
        chip.click();
        await flush();
        expect(chip.getAttribute('aria-pressed')).toBe('true');
        expect(chip.classList.contains('active')).toBe(true);
    });

    it('clicking the active chip clears the filter', async () => {
        await boot();
        const chip = document.querySelector('#filters .filter-tag');
        chip.click();
        chip.click();
        await flush();
        expect(chip.getAttribute('aria-pressed')).toBe('false');
    });

    it('only one chip is active at a time', async () => {
        await boot();
        const [first, second] = document.querySelectorAll('#filters .filter-tag');
        first.click();
        second.click();
        await flush();
        expect(first.getAttribute('aria-pressed')).toBe('false');
        expect(second.getAttribute('aria-pressed')).toBe('true');
    });
});

describe('URL state', () => {
    it('puts the query in the address bar', async () => {
        await boot();
        submitSearch('vector database');
        await flush();
        expect(window.location.search).toContain('q=vector+database');
    });

    it('runs the search named in the URL on load', async () => {
        window.history.replaceState({}, '', '/?q=from+the+url');
        const calls = await boot();

        const search = calls.find(c => c.url.includes('/api/search'));
        expect(JSON.parse(search.options.body).query).toBe('from the url');
        expect(document.getElementById('searchInput').value).toBe('from the url');
    });

    it('restores a category from the URL', async () => {
        window.history.replaceState({}, '', '/?q=x&category=Research');
        const calls = await boot();

        const search = calls.find(c => c.url.includes('/api/search'));
        expect(JSON.parse(search.options.body).category).toBe('Research');

        const research = [...document.querySelectorAll('#filters .filter-tag')]
            .find(c => c.dataset.category === 'Research');
        expect(research.getAttribute('aria-pressed')).toBe('true');
    });

    it('does not push a duplicate entry when restoring history', async () => {
        await boot();
        submitSearch('one');
        await flush();
        const length = window.history.length;

        window.dispatchEvent(new window.PopStateEvent('popstate', { state: { query: 'one', category: null } }));
        await flush();
        expect(window.history.length).toBe(length);
    });
});

describe('copy link', () => {
    it('offers a copy button once results are shown', async () => {
        await boot();
        submitSearch('code editor');
        await flush();
        expect(document.querySelector('.copy-link')).not.toBeNull();
    });

    it('copies the shareable URL', async () => {
        const written = [];
        Object.defineProperty(navigator, 'clipboard', {
            value: { writeText: (t) => { written.push(t); return Promise.resolve(); } },
            configurable: true,
        });
        Object.defineProperty(window, 'isSecureContext', { value: true, configurable: true });

        await boot();
        submitSearch('vector search');
        await flush();

        document.querySelector('.copy-link').click();
        await flush();

        expect(written).toHaveLength(1);
        expect(written[0]).toContain('q=vector+search');
        expect(document.querySelector('.copy-link').textContent).toBe('Copied');
    });

    it('reports a failure instead of silently doing nothing', async () => {
        Object.defineProperty(navigator, 'clipboard', {
            value: { writeText: () => Promise.reject(new Error('denied')) },
            configurable: true,
        });
        Object.defineProperty(window, 'isSecureContext', { value: true, configurable: true });

        await boot();
        submitSearch('anything');
        await flush();

        document.querySelector('.copy-link').click();
        await flush();

        expect(document.querySelector('.copy-link').textContent).toContain('Ctrl+C');
    });

    it('is not shown when there are no results', async () => {
        await boot(defaultRoutes({
            '/api/search': { body: { results: [], metadata: { confident: false } } },
        }));
        submitSearch('nothing');
        await flush();
        expect(document.querySelector('.copy-link')).toBeNull();
    });
});

describe('retrying a failed search', () => {
    it('offers a retry when the server errors', async () => {
        await boot(defaultRoutes({
            '/api/search': { ok: false, status: 500, body: { error: 'Internal server error' } },
        }));
        submitSearch('anything');
        await flush();
        expect(document.querySelector('.retry-btn')).not.toBeNull();
    });

    it('offers a retry when the network is down', async () => {
        await boot(defaultRoutes({ '/api/search': new Error('offline') }));
        submitSearch('anything');
        await flush();

        const button = document.querySelector('.retry-btn');
        expect(button).not.toBeNull();
        expect(document.querySelector('.result-message').textContent).toContain('Could not reach');
    });

    it('does not offer a retry for a client error', async () => {
        await boot(defaultRoutes({
            '/api/search': { ok: false, status: 400, body: { error: 'query too long' } },
        }));
        submitSearch('anything');
        await flush();
        expect(document.querySelector('.retry-btn')).toBeNull();
        expect(document.querySelector('.result-message').textContent).toContain('query too long');
    });

    it('succeeds on retry once the server recovers', async () => {
        let attempt = 0;
        await boot(defaultRoutes({
            '/api/search': () => {
                attempt += 1;
                return attempt === 1
                    ? { ok: false, status: 500, body: { error: 'boom' } }
                    : { body: { results: [makeResult('Cursor')], metadata: { confident: true } } };
            },
        }));
        submitSearch('code editor');
        await flush();

        document.querySelector('.retry-btn').click();
        await flush();

        expect(document.querySelector('.retry-btn')).toBeNull();
        expect(document.querySelector('.agent-name').textContent).toBe('Cursor');
    });

    it('moves focus to the retry button so keyboard users can reach it', async () => {
        await boot(defaultRoutes({ '/api/search': new Error('offline') }));
        submitSearch('anything');
        await flush();
        expect(document.activeElement).toBe(document.querySelector('.retry-btn'));
    });
});

describe('recent searches', () => {
    beforeEach(() => localStorage.clear());
    afterEach(() => localStorage.clear());

    it('is hidden with no history', async () => {
        await boot();
        expect(document.getElementById('recent').hidden).toBe(true);
    });

    it('records a search and shows it as a chip', async () => {
        await boot();
        submitSearch('vector database');
        await flush();

        expect(document.getElementById('recent').hidden).toBe(false);
        const chips = [...document.querySelectorAll('.recent-item')].map(c => c.textContent);
        expect(chips).toContain('vector database');
    });

    it('includes the active category in the chip label', async () => {
        await boot();
        document.querySelector('#filters .filter-tag').click();
        submitSearch('editor');
        await flush();
        expect(document.querySelector('.recent-item').textContent).toContain('Code Generation');
    });

    it('re-runs a search when its chip is clicked', async () => {
        const calls = await boot();
        submitSearch('first query');
        await flush();

        document.getElementById('searchInput').value = '';
        document.querySelector('.recent-item').click();
        await flush();

        expect(document.getElementById('searchInput').value).toBe('first query');
        const last = calls.filter(c => c.url.includes('/api/search')).pop();
        expect(JSON.parse(last.options.body).query).toBe('first query');
    });

    it('does not record a search replayed from the URL', async () => {
        window.history.replaceState({}, '', '/?q=from+url');
        await boot();
        expect(document.getElementById('recent').hidden).toBe(true);
    });

    it('clears the history', async () => {
        await boot();
        submitSearch('something');
        await flush();

        document.getElementById('recentClear').click();
        await flush();
        expect(document.getElementById('recent').hidden).toBe(true);
    });
});

describe('exporting results', () => {
    it('offers CSV and JSON once results are shown', async () => {
        await boot();
        submitSearch('code editor');
        await flush();
        const labels = [...document.querySelectorAll('.export-btn')].map(b => b.textContent);
        expect(labels).toEqual(['Export CSV', 'Export JSON']);
    });

    it('is not offered when there are no results', async () => {
        await boot(defaultRoutes({
            '/api/search': { body: { results: [], metadata: { confident: false } } },
        }));
        submitSearch('nothing');
        await flush();
        expect(document.querySelector('.export-btn')).toBeNull();
    });

    it('downloads a file named after the query', async () => {
        const clicked = [];
        URL.createObjectURL = () => 'blob:fake';
        URL.revokeObjectURL = () => {};
        const realClick = HTMLAnchorElement.prototype.click;
        HTMLAnchorElement.prototype.click = function () { clicked.push(this.download); };

        try {
            await boot();
            submitSearch('code editor');
            await flush();
            document.querySelector('.export-btn').click();
            expect(clicked).toEqual(['code-editor.csv']);
        } finally {
            HTMLAnchorElement.prototype.click = realClick;
        }
    });

    it('reports a failure instead of doing nothing', async () => {
        URL.createObjectURL = () => { throw new Error('blocked'); };
        await boot();
        submitSearch('code editor');
        await flush();

        const button = document.querySelector('.export-btn');
        button.click();
        expect(button.textContent).toBe('Export failed');
    });
});

describe('name suggestions', () => {
    function type(value) {
        const input = document.getElementById('searchInput');
        input.value = value;
        input.dispatchEvent(new window.Event('input'));
    }

    function press(key) {
        const event = new window.KeyboardEvent('keydown', { key, bubbles: true, cancelable: true });
        document.getElementById('searchInput').dispatchEvent(event);
        return event;
    }

    function suggestionRoutes() {
        return defaultRoutes({
            '/api/agents': { body: {
                agents: [makeResult('ComfyUI'), makeResult('Cursor'), makeResult('Vocode')],
                metadata: { total: 3, has_more: false },
            } },
        });
    }

    it('offers matching names as you type', async () => {
        await boot(suggestionRoutes());
        type('cu');
        const items = [...document.querySelectorAll('.suggestion')].map(i => i.textContent);
        expect(items).toEqual(['Cursor']);
        expect(document.getElementById('suggestions').hidden).toBe(false);
    });

    it('highlights the matched span', async () => {
        await boot(suggestionRoutes());
        type('urs');
        expect(document.querySelector('.suggestion mark').textContent).toBe('urs');
    });

    it('hides when nothing matches', async () => {
        await boot(suggestionRoutes());
        type('zzzz');
        expect(document.getElementById('suggestions').hidden).toBe(true);
    });

    it('hides when the box is emptied', async () => {
        await boot(suggestionRoutes());
        type('cu');
        type('');
        expect(document.getElementById('suggestions').hidden).toBe(true);
    });

    it('moves through the list with the arrow keys', async () => {
        await boot(suggestionRoutes());
        type('c');
        press('ArrowDown');
        expect(document.querySelectorAll('.suggestion')[0].classList.contains('active')).toBe(true);
        press('ArrowDown');
        expect(document.querySelectorAll('.suggestion')[1].classList.contains('active')).toBe(true);
    });

    it('searches for the highlighted name on Enter', async () => {
        const calls = await boot(suggestionRoutes());
        type('c');
        press('ArrowDown');
        press('Enter');
        await flush();

        expect(document.getElementById('searchInput').value).toBe('ComfyUI');
        const search = calls.filter(c => c.url.includes('/api/search')).pop();
        expect(JSON.parse(search.options.body).query).toBe('ComfyUI');
    });

    it('Escape closes the list without searching', async () => {
        const calls = await boot(suggestionRoutes());
        type('c');
        const before = calls.filter(c => c.url.includes('/api/search')).length;
        press('Escape');

        expect(document.getElementById('suggestions').hidden).toBe(true);
        expect(calls.filter(c => c.url.includes('/api/search')).length).toBe(before);
    });

    it('clicking a suggestion searches for it', async () => {
        const calls = await boot(suggestionRoutes());
        type('cu');
        document.querySelector('.suggestion').dispatchEvent(
            new window.MouseEvent('mousedown', { bubbles: true, cancelable: true }));
        await flush();

        const search = calls.filter(c => c.url.includes('/api/search')).pop();
        expect(JSON.parse(search.options.body).query).toBe('Cursor');
    });

    it('exposes combobox state to assistive tech', async () => {
        await boot(suggestionRoutes());
        const input = document.getElementById('searchInput');
        expect(input.getAttribute('aria-expanded')).toBe('false');

        type('c');
        expect(input.getAttribute('aria-expanded')).toBe('true');

        press('ArrowDown');
        expect(input.getAttribute('aria-activedescendant')).toBe('suggestion-0');
    });

    it('submitting normally still runs a semantic search', async () => {
        const calls = await boot(suggestionRoutes());
        type('something vague');
        submitSearch('something vague');
        await flush();

        expect(document.getElementById('suggestions').hidden).toBe(true);
        const search = calls.filter(c => c.url.includes('/api/search')).pop();
        expect(JSON.parse(search.options.body).query).toBe('something vague');
    });
});

describe('loading every suggestable name', () => {
    // The preview grid also calls /api/agents (limit=6); only the limit=200
    // requests belong to the suggestion loader.
    const pageCalls = (calls) => calls.filter(c => c.url.includes('limit=200'));

    it('follows pagination past the server cap', async () => {
        // The server caps limit; a single request would truncate silently.
        let page = 0;
        const calls = await boot(defaultRoutes({
            '/api/agents': (url) => {
                if (!url.includes('limit=200')) {
                    return { body: { agents: [], metadata: { total: 0, has_more: false } } };
                }
                page += 1;
                return page === 1
                    ? { body: { agents: [makeResult('Aardvark')], metadata: { total: 2, has_more: true } } }
                    : { body: { agents: [makeResult('Zebra')], metadata: { total: 2, has_more: false } } };
            },
        }));

        const agentCalls = pageCalls(calls);
        expect(agentCalls.length).toBeGreaterThanOrEqual(2);
        expect(agentCalls[1].url).toContain('offset=1');

        document.getElementById('searchInput').value = 'zeb';
        document.getElementById('searchInput').dispatchEvent(new window.Event('input'));
        expect([...document.querySelectorAll('.suggestion')].map(i => i.textContent)).toEqual(['Zebra']);
    });

    it('stops when there are no more pages', async () => {
        const calls = await boot(defaultRoutes({
            '/api/agents': { body: { agents: [makeResult('Only')], metadata: { total: 1, has_more: false } } },
        }));
        expect(pageCalls(calls).length).toBe(1);
    });

    it('keeps whatever arrived when a later page fails', async () => {
        let page = 0;
        await boot(defaultRoutes({
            '/api/agents': (url) => {
                if (!url.includes('limit=200')) {
                    return { body: { agents: [], metadata: { has_more: false } } };
                }
                page += 1;
                return page === 1
                    ? { body: { agents: [makeResult('First')], metadata: { has_more: true } } }
                    : new Error('offline');
            },
        }));

        document.getElementById('searchInput').value = 'fir';
        document.getElementById('searchInput').dispatchEvent(new window.Event('input'));
        expect([...document.querySelectorAll('.suggestion')].map(i => i.textContent)).toEqual(['First']);
    });

    it('does not loop forever if has_more never clears', async () => {
        const calls = await boot(defaultRoutes({
            '/api/agents': { body: { agents: [makeResult('Loop')], metadata: { has_more: true } } },
        }));
        // AgentsApi caps the walk; the exact number is its business.
        expect(pageCalls(calls).length).toBeLessThanOrEqual(globalThis.AgentsApi.MAX_PAGES);
    });
});

describe('when nothing matches well', () => {
    const weak = () => defaultRoutes({
        '/api/search': { body: { results: [makeResult('Cursor', 0.3)], metadata: { confident: false } } },
    });

    it('offers categories to browse instead of a dead end', async () => {
        await boot(weak());
        submitSearch('banana bread');
        await flush();

        const notice = document.querySelector('.result-notice');
        expect(notice.textContent).toContain('Nothing matched');
        const links = [...notice.querySelectorAll('a')].map(a => a.textContent);
        expect(links).toEqual(['Code Generation', 'Research']);
    });

    it('links each suggestion to its category page', async () => {
        await boot(weak());
        submitSearch('banana bread');
        await flush();
        expect(document.querySelector('.result-notice a').getAttribute('href'))
            .toBe('/category/Code%20Generation');
    });

    it('still shows the notice when categories failed to load', async () => {
        await boot(defaultRoutes({
            '/api/categories': new Error('offline'),
            '/api/search': { body: { results: [makeResult('X', 0.2)], metadata: { confident: false } } },
        }));
        submitSearch('banana bread');
        await flush();

        const notice = document.querySelector('.result-notice');
        expect(notice.textContent).toContain('Nothing matched');
        expect(notice.querySelector('a')).toBeNull();
    });

    it('adds no suggestion when the match was confident', async () => {
        await boot();
        submitSearch('code editor');
        await flush();
        expect(document.querySelector('.result-notice')).toBeNull();
    });
});

describe('saving a search', () => {
    it('offers to save once results are shown', async () => {
        await boot();
        submitSearch('code editor');
        await flush();

        expect(document.querySelector('.save-search-btn').textContent).toBe('Save this search');
    });

    it('saves the query with its results', async () => {
        await boot();
        submitSearch('code editor');
        await flush();
        document.querySelector('.save-search-btn').click();

        const [entry] = globalThis.SavedSearches.list();
        expect(entry.query).toBe('code editor');
        expect(entry.snapshot.names.length).toBeGreaterThan(0);
    });

    it('says so once saved', async () => {
        await boot();
        submitSearch('code editor');
        await flush();
        const button = document.querySelector('.save-search-btn');
        button.click();

        expect(button.textContent).toBe('Saved ✓');
    });

    it('a second click undoes it', async () => {
        /** The button is the only affordance for this query; one-way would
         *  send someone to another page to undo a misclick. */
        await boot();
        submitSearch('code editor');
        await flush();
        const button = document.querySelector('.save-search-btn');

        button.click();
        button.click();

        expect(globalThis.SavedSearches.list()).toEqual([]);
        expect(button.textContent).toBe('Save this search');
    });

    it('shows an already-saved query as saved', async () => {
        await boot();
        globalThis.SavedSearches.save('code editor', null, [{ name: 'A', metadata: { name: 'A' } }]);

        submitSearch('code editor');
        await flush();

        expect(document.querySelector('.save-search-btn').textContent).toBe('Saved ✓');
    });

    it('is not one of the export controls', async () => {
        await boot();
        submitSearch('code editor');
        await flush();

        expect([...document.querySelectorAll('.export-btn')].map(b => b.textContent))
            .toEqual(['Export CSV', 'Export JSON']);
    });
});

describe('saving records the filter that produced the results', () => {
    it('a filter set after the results does not relabel them', async () => {
        /** The button captured the query and results but read the live
         *  activeCategory at click time. With the input empty a chip only
         *  sets the filter and rewrites the URL — the old results bar stays
         *  on screen — so saving paired an unfiltered snapshot with a
         *  category, and the first check on /saved reported nearly every
         *  result as "No longer matches". */
        await boot();
        submitSearch('rag');
        await flush();

        // Empty input: the chip changes activeCategory without re-searching,
        // and the bar from the unfiltered search is still displayed.
        document.getElementById('searchInput').value = '';
        [...document.querySelectorAll('#filters .filter-tag')]
            .find(b => b.textContent.includes('Research')).click();
        await flush();

        document.querySelector('.save-search-btn').click();

        const [entry] = globalThis.SavedSearches.list();
        expect(entry.category).toBe('');
    });

    it('a filtered search saves under its filter', async () => {
        await boot();
        [...document.querySelectorAll('#filters .filter-tag')]
            .find(b => b.textContent.includes('Research')).click();
        await flush();

        submitSearch('rag');
        await flush();
        document.querySelector('.save-search-btn').click();

        expect(globalThis.SavedSearches.list()[0].category).toBe('Research');
    });

    it('uses the filter that was sent, not one chosen mid-request', async () => {
        /** The results arrive asynchronously; activeCategory can change in
         *  between. The saved entry must describe the request that produced
         *  these results. */
        await boot();
        submitSearch('rag');

        // Change the filter while the search is still in flight.
        document.getElementById('searchInput').value = '';
        [...document.querySelectorAll('#filters .filter-tag')]
            .find(b => b.textContent.includes('Research')).click();
        await flush();

        document.querySelector('.save-search-btn').click();
        expect(globalThis.SavedSearches.list()[0].category).toBe('');
    });
});

describe('hiding abandoned projects', () => {
    it('does not ask for the filter by default', async () => {
        const calls = await boot();
        submitSearch('agent');
        await flush();

        const sent = JSON.parse(calls.find(c => c.url.includes('/api/search')).options.body);
        expect(sent.maintained).toBeUndefined();
    });

    it('asks for it when the toggle is on', async () => {
        const calls = await boot();
        document.getElementById('maintainedOnly').checked = true;
        submitSearch('agent');
        await flush();

        const sent = JSON.parse(calls.find(c => c.url.includes('/api/search')).options.body);
        expect(sent.maintained).toBe(true);
    });

    it('keeps the filter on a follow-up search', async () => {
        const calls = await boot();
        document.getElementById('maintainedOnly').checked = true;
        submitSearch('agent');
        await flush();
        submitSearch('another');
        await flush();

        const bodies = calls.filter(c => c.url.includes('/api/search'))
            .map(c => JSON.parse(c.options.body));
        expect(bodies.every(b => b.maintained === true)).toBe(true);
    });

    it('has a label a screen reader can use', async () => {
        await boot();
        const label = document.querySelector('label[for="maintainedOnly"]');
        expect(label.textContent.trim()).toContain('maintained');
    });
});

describe('the maintained toggle takes effect immediately', () => {
    it('re-runs the current search when ticked', async () => {
        /** A filter that only applies to the *next* search is a filter
         *  people reasonably think is broken. Category chips re-search on
         *  click; this now behaves the same way. */
        const calls = await boot();
        submitSearch('agent');
        await flush();
        const before = calls.filter(c => c.url.includes('/api/search')).length;

        const toggle = document.getElementById('maintainedOnly');
        toggle.checked = true;
        toggle.dispatchEvent(new window.Event('change'));
        await flush();

        // The summary is a second request to the same path, so count "more
        // than before" rather than an exact number.
        const searches = calls.filter(c => c.url.includes('/api/search'));
        expect(searches.length).toBeGreaterThan(before);
        expect(JSON.parse(searches.at(-1).options.body).maintained).toBe(true);
    });

    it('reloads the browse grid when there is no query', async () => {
        const calls = await boot();

        const toggle = document.getElementById('maintainedOnly');
        toggle.checked = true;
        toggle.dispatchEvent(new window.Event('change'));
        await flush();

        const listing = calls.filter(c => c.url.includes('/api/agents')).at(-1);
        expect(listing.url).toContain('maintained=1');
    });

    it('does not ask the listing to filter when it is off', async () => {
        const calls = await boot();
        const listing = calls.filter(c => c.url.includes('/api/agents')).at(-1);
        expect(listing.url).not.toContain('maintained');
    });
});

describe('the health filter travels with the link', () => {
    it('restores the toggle from a shared URL', async () => {
        /** "Copy link" is advertised as reproducing the results; a link that
         *  drops the filter reproduces different ones. */
        window.history.replaceState({}, '', '/?q=agent&maintained=1');
        await boot();

        expect(document.getElementById('maintainedOnly').checked).toBe(true);
    });

    it('puts it in the URL when a filtered search runs', async () => {
        await boot();
        document.getElementById('maintainedOnly').checked = true;
        submitSearch('agent');
        await flush();

        expect(window.location.search).toContain('maintained=1');
    });

    it('leaves a plain search with a plain URL', async () => {
        await boot();
        submitSearch('agent');
        await flush();

        expect(window.location.search).not.toContain('maintained');
    });

    it('records the filter on a saved search', async () => {
        /** The snapshot was taken with it applied; /saved re-running without
         *  it would report every excluded project as brand new. */
        await boot();
        document.getElementById('maintainedOnly').checked = true;
        submitSearch('agent');
        await flush();
        document.querySelector('.save-search-btn').click();

        expect(globalThis.SavedSearches.list()[0].maintained).toBe(true);
    });

    it('an unfiltered save records it as off', async () => {
        await boot();
        submitSearch('agent');
        await flush();
        document.querySelector('.save-search-btn').click();

        expect(globalThis.SavedSearches.list()[0].maintained).toBe(false);
    });
});
