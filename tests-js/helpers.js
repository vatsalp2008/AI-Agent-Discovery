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

/** agent-card.js renders result tiles and is loaded by every page. */
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
 * The scripts a template loads, in order, excluding the page script itself.
 *
 * Reading this from the template rather than restating it in each test means
 * adding a dependency cannot leave a test booting an incomplete page — which
 * it would only notice if the missing global happened to be used during boot.
 */
export function scriptsFor(templateName, pageScript) {
    const TEMPLATES = resolve(here, '..', 'ai-agent-discovery', 'frontend', 'templates');

    // Read the global from the file rather than deriving it from the name:
    // ui.js defines UI, not Ui, and any such acronym would break the guess.
    const globalFor = (file) => {
        const source = readFileSync(resolve(STATIC_JS, file), 'utf8');
        const declared = source.match(/^const (\w+) = \(\(\) => \{/m);
        return declared ? declared[1] : null;
    };

    const read = (name) => readFileSync(resolve(TEMPLATES, name), 'utf8');
    const sources = [read('base.html'), read(templateName)].join('\n');

    return [...sources.matchAll(/<script src="\/static\/js\/([^"]+)"/g)]
        .map(m => m[1])
        .filter(file => file !== pageScript)
        .map(file => ({ file, global: globalFor(file) }))
        // Scripts that define no global (page scripts pulled in by base.html,
        // like shortcuts.js) still need loading, just not exposing.
        .filter(entry => entry.global !== null);
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
    // base.html loads ui.js before every page script.
    loadScript('ui.js', 'UI');
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
 * Stub `fetch`. Records every call so tests can assert what the page
 * actually requested.
 *
 * A route key may be prefixed with a method — `'POST /api/search'` — and the
 * stub then refuses a request that uses a different one, the way the server
 * would with a 405. Without that, `/saved` shipped calling POST-only
 * `/api/search` with a GET: every test passed and the feature was dead.
 */
export function stubFetch(routes) {
    const calls = [];
    globalThis.fetch = (url, options) => {
        calls.push({ url: String(url), options });
        const method = (options?.method || 'GET').toUpperCase();

        const match = Object.keys(routes).find(key => {
            const [maybeMethod, ...rest] = key.split(' ');
            if (rest.length) return maybeMethod.toUpperCase() === method
                && String(url).includes(rest.join(' '));
            return String(url).includes(key);
        });
        if (!match) {
            return Promise.reject(new Error(`unrouted fetch: ${method} ${url}`));
        }

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
      <label class="sr-only" for="searchInput">Search for an AI agent</label>
      <input id="searchInput" type="search" role="combobox" aria-expanded="false">
      <ul id="suggestions" role="listbox" aria-label="Matching agent names" hidden></ul>
      <button id="searchBtn" type="submit">go</button>
    </form>
    <div id="filters"></div>
    <div class="search-options">
      <label class="option-toggle" for="maintainedOnly">
        <input type="checkbox" id="maintainedOnly">
        Only maintained projects
      </label>
    </div>
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
    <div class="category-grid" id="categoryTiles"></div>
    <div class="controls">
      <label class="sr-only" for="filterQuery">Filter by name or description</label>
      <input type="search" id="filterQuery">
      <label class="sr-only" for="filterCategory">Category</label>
      <select id="filterCategory"><option value="">All categories</option></select>
      <label class="sr-only" for="filterTech">Technology</label>
      <select id="filterTech"><option value="">All technologies</option></select>
      <label class="sr-only" for="sortBy">Sort by</label>
      <select id="sortBy"><option value="name">Name</option><option value="stars">Stars</option></select>
      <button type="button" id="sortOrder" aria-label="Sort ascending">↑</button>
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
      <label class="sr-only" for="comparePick">Add an agent</label>
      <select id="comparePick"><option value="">Add an agent…</option></select>
      <button type="button" id="compareClear">Clear</button>
    </div>
    <main id="compareArea" aria-busy="false"></main>
`;

/** The change history page's markup, mirroring templates/changes.html. */
export const CHANGES_HTML = `
    <main id="changesArea" aria-live="polite" aria-busy="true"></main>
`;

/** The technology page's markup, mirroring templates/tech.html. */
export const TECH_HTML = `
    <h1 id="techHeading">Python</h1>
    <p id="techCount">Loading…</p>
    <div id="techOther" class="filters"></div>
    <main id="techGrid" class="results-grid" aria-live="polite" aria-busy="true"></main>
`;

/** The saved searches page's markup, mirroring templates/saved.html. */
export const SAVED_HTML = `
    <button type="button" id="checkAll">Check for changes</button>
    <button type="button" id="clearSaved">Remove all</button>
    <button type="button" id="exportSaved">Export</button>
    <label class="control-button" for="importSaved">Import
      <input type="file" id="importSaved" class="sr-only">
    </label>
    <div id="savedResult" aria-live="polite"></div>
    <main id="savedArea" aria-live="polite" aria-busy="false"></main>
`;

/** The collections page's markup, mirroring templates/collections.html. */
export const COLLECTIONS_HTML = `
    <form id="newCollectionForm">
      <label class="sr-only" for="newCollectionName">New collection name</label>
      <input type="text" id="newCollectionName">
      <button type="submit">Create</button>
    </form>
    <button type="button" id="exportCollections">Export</button>
    <label class="control-button" for="importCollections">Import
      <input type="file" id="importCollections" class="sr-only">
    </label>
    <div id="collectionsResult" aria-live="polite"></div>
    <main id="collectionsArea"></main>
`;

/** The catalogue editor's markup, mirroring templates/admin.html. */
export const ADMIN_HTML = `
    <p id="adminDisabled" hidden></p>
    <div id="adminPanel" hidden>
      <div class="admin-bar">
        <span id="adminCount"></span>
        <span id="adminStale" hidden></span>
        <button type="button" id="undoBtn">Undo last change</button>
        <button type="button" id="reindexBtn">Rebuild index</button>
      </div>
      <div id="adminResult" aria-live="polite"></div>
      <form id="agentForm">
        <h2 id="formHeading">Add an agent</h2>
        <input type="hidden" id="editingName" value="">
        <label for="fieldName">Name</label>
        <input type="text" id="fieldName">
        <label for="fieldCategory">Category</label>
        <input type="text" id="fieldCategory">
        <datalist id="categoryOptions"></datalist>
        <label for="fieldDescription">Description</label>
        <textarea id="fieldDescription"></textarea>
        <label for="fieldStack">Tech stack</label>
        <input type="text" id="fieldStack">
        <label for="fieldStars">GitHub stars</label>
        <input type="number" id="fieldStars" value="0">
        <label for="fieldUrl">URL</label>
        <input type="url" id="fieldUrl">
        <label for="fieldUseCase">Use case</label>
        <input type="text" id="fieldUseCase">
        <button type="submit" id="saveBtn">Add agent</button>
        <button type="button" id="cancelBtn" hidden>Cancel</button>
      </form>
      <label class="sr-only" for="adminFilter">Filter agents</label>
      <section id="submissionsSection" hidden>
        <span id="submissionsCount"></span>
        <div id="submissionsList"></div>
      </section>
      <input type="search" id="adminFilter">
      <span id="adminFilterCount"></span>
      <div id="adminList"></div>
      <div id="auditList"></div>
    </div>
`;

/** The category browse page's markup, mirroring templates/category.html. */
export const CATEGORY_HTML = `
    <h1 id="categoryHeading">Evaluation</h1>
    <p id="categoryCount">Loading…</p>
    <div id="categoryOther"></div>
    <main id="categoryGrid" aria-busy="true"></main>
`;

/** The submission form's markup, mirroring templates/submit.html. */
export const SUBMIT_HTML = `
    <p id="submitClosed" hidden></p>
    <form id="submitForm">
      <div id="submitResult" aria-live="polite"></div>
      <label for="submitName">Name</label>
      <input type="text" id="submitName">
      <label for="submitCategory">Category</label>
      <input type="text" id="submitCategory" list="submitCategories">
      <datalist id="submitCategories"></datalist>
      <label for="submitDescription">Description</label>
      <textarea id="submitDescription"></textarea>
      <label for="submitStack">Tech stack</label>
      <input type="text" id="submitStack">
      <label for="submitUrl">URL</label>
      <input type="url" id="submitUrl">
      <label for="submitUseCase">Use case</label>
      <input type="text" id="submitUseCase">
      <button type="submit" id="submitBtn">Submit for review</button>
    </form>
`;
