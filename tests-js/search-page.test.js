/**
 * Wiring tests for main.js: the parts that talk to the DOM and the API.
 * The pure helpers are covered in search-state.test.js.
 */

import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { bootPage, flush, SEARCH_HTML, stubFetch } from './helpers.js';

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
        // index.html loads search-state.js before main.js.
        extraScripts: [
            { file: 'search-state.js', global: 'SearchState' },
            { file: 'recent-searches.js', global: 'RecentSearches' },
            { file: 'export-results.js', global: 'ExportResults' },
        ],
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
