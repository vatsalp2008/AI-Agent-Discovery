import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const STATIC_JS = resolve(here, '..', 'ai-agent-discovery', 'frontend', 'static', 'js');

/**
 * The static scripts are plain files that assign a global, not ES modules.
 * Evaluate one in the jsdom window so tests exercise exactly the file the
 * browser loads, with no build step or source duplication.
 */
export function loadScript(filename, globalName) {
    const source = readFileSync(resolve(STATIC_JS, filename), 'utf8');
    // eslint-disable-next-line no-eval
    (0, eval)(`${source}\n;globalThis.${globalName} = ${globalName};`);
    return globalThis[globalName];
}

export function loadAgentCard() {
    return loadScript('agent-card.js', 'AgentCard');
}

/** Minimal agent record shaped like a /api/search result. */
export function makeAgent(overrides = {}) {
    return {
        name: 'Cursor',
        description: 'An AI-powered code editor.',
        score: 0.91,
        metadata: {
            name: 'Cursor',
            category: 'Code Generation',
            stack: 'Electron,GPT-4,VS Code',
            stars: 35000,
            description: 'An AI-powered code editor.',
            url: 'https://cursor.sh',
        },
        ...overrides,
    };
}

/**
 * Boot a page script the way the browser does: install the markup, evaluate
 * agent-card.js (which every page loads), then evaluate the page script and
 * fire DOMContentLoaded.
 *
 * Returns once the listener's synchronous part has run; awaiting `flush()`
 * lets any fetch chains it kicked off settle.
 */
export function bootPage({ html, script, extraScripts = [] }) {
    document.body.innerHTML = html;
    loadAgentCard();
    extraScripts.forEach(({ file, global }) => loadScript(file, global));

    // Capture the page's DOMContentLoaded handler instead of registering it.
    // Registering would leave the listener attached to the shared jsdom
    // document, so a later bootPage would run every earlier page instance too
    // and they would fight over the same elements.
    const handlers = [];
    const realAdd = document.addEventListener.bind(document);
    document.addEventListener = (type, fn, ...rest) => {
        if (type === 'DOMContentLoaded') handlers.push(fn);
        else realAdd(type, fn, ...rest);
    };

    try {
        const source = readFileSync(resolve(STATIC_JS, script), 'utf8');
        // Surface any top-level const the file defines (e.g. Theme) so tests
        // can drive its API directly, the same way loadScript does.
        const exposed = script.replace(/\.js$/, '').replace(/(^|-)(\w)/g, (_, __, c) => c.toUpperCase());
        // eslint-disable-next-line no-eval
        (0, eval)(`${source}\n;try { globalThis.${exposed} = ${exposed}; } catch (e) {}`);
    } finally {
        document.addEventListener = realAdd;
    }

    handlers.forEach(fn => fn(new window.Event('DOMContentLoaded')));
}

/** Let pending promise chains (fetch handlers) run to completion. */
export async function flush(times = 6) {
    for (let i = 0; i < times; i += 1) {
        await Promise.resolve();
        await new Promise(r => setTimeout(r, 0));
    }
}

/**
 * A fetch stub routed by URL substring. Records every call so tests can assert
 * what the page actually requested.
 */
export function stubFetch(routes) {
    const calls = [];
    globalThis.fetch = (url, options) => {
        calls.push({ url: String(url), options });
        const match = Object.keys(routes).find(key => String(url).includes(key));
        if (!match) return Promise.reject(new Error(`unrouted fetch: ${url}`));

        const route = routes[match];
        const value = typeof route === 'function' ? route(String(url), options) : route;
        if (value instanceof Error) return Promise.reject(value);

        return Promise.resolve({
            ok: value.ok !== false,
            status: value.status || 200,
            json: () => Promise.resolve(value.body),
        });
    };
    return calls;
}

/** The search page's markup, mirroring templates/index.html. */
export const SEARCH_HTML = `
    <form id="searchForm">
      <input id="searchInput" type="search">
      <button id="searchBtn" type="submit">go</button>
    </form>
    <div id="filters"></div>
    <div class="recent" id="recent" hidden>
      <span id="recentLabel">Recent</span>
      <span id="recentList"></span>
      <button type="button" id="recentClear">Clear</button>
    </div>
    <main id="resultsArea" aria-live="polite" aria-busy="false"></main>
`;

/** The dashboard's markup, mirroring templates/dashboard.html. */
export const DASHBOARD_HTML = `
    <div class="stats-grid" id="statsGrid" aria-busy="true">
      <div class="stat-number" id="totalAgents">-</div>
      <div class="stat-number" id="topCategory">-</div>
      <div class="stat-number" id="totalStars">-</div>
    </div>
    <div class="controls">
      <input type="search" id="filterQuery">
      <select id="filterCategory"><option value="">All categories</option></select>
      <select id="filterTech"><option value="">All technologies</option></select>
      <select id="sortBy"><option value="name">Name</option><option value="stars">Stars</option></select>
      <button type="button" id="sortOrder">↑</button>
    </div>
    <div class="results-grid" id="allAgentsGrid" aria-busy="true"></div>
    <div class="grid-footer" id="gridFooter"></div>
`;

/** The agent detail page's markup, mirroring templates/agent.html. */
export const AGENT_HTML = `
    <nav class="breadcrumb"><a href="/">Search</a> <span id="crumbName">x</span></nav>
    <div id="agentDetail" aria-busy="true"></div>
    <section id="similarSection" hidden>
      <h2 id="similarHeading">Similar agents</h2>
      <div id="similarGrid"></div>
    </section>
`;

/** The comparison page's markup, mirroring templates/compare.html. */
export const COMPARE_HTML = `
    <div class="controls">
      <select id="comparePick"><option value="">Add an agent…</option></select>
      <button type="button" id="compareClear">Clear</button>
    </div>
    <main id="compareArea" aria-busy="false"></main>
`;
