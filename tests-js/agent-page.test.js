/** Wiring tests for agent.js, the /agent/<name> detail page. */

import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { AGENT_HTML, bootPage, flush, stubFetch } from './helpers.js';

const CURSOR = {
    name: 'Cursor',
    description: 'An AI-powered code editor.',
    metadata: {
        name: 'Cursor',
        category: 'Code Generation',
        stack: 'Electron,GPT-4,VS Code',
        stars: 35000,
        description: 'An AI-powered code editor.',
        url: 'https://cursor.sh',
    },
};

function similar(name) {
    return { name, score: 0.8, metadata: { name, category: 'Code Generation', stack: 'Python', stars: 1, description: `${name} d.` } };
}

function routes(overrides = {}) {
    return {
        '/similar': { body: { agents: [similar('Aider'), similar('Cline')], metadata: { of: 'Cursor', count: 2 } } },
        '/api/agents/': { body: CURSOR },
        ...overrides,
    };
}

async function boot(path = '/agent/Cursor', r = routes()) {
    window.history.replaceState({}, '', path);
    const calls = stubFetch(r);
    bootPage({ html: AGENT_HTML, script: 'agent.js' });
    await flush();
    return calls;
}

beforeEach(() => window.history.replaceState({}, '', '/'));
afterEach(() => { delete globalThis.fetch; });

describe('loading the agent', () => {
    it('requests the agent named in the path', async () => {
        const calls = await boot('/agent/Cursor');
        expect(calls[0].url).toContain('/api/agents/Cursor');
    });

    it('decodes a name with spaces', async () => {
        const calls = await boot('/agent/Claude%20Code');
        expect(decodeURIComponent(calls[0].url)).toContain('/api/agents/Claude Code');
    });

    it('renders the agent details', async () => {
        await boot();
        const text = document.getElementById('agentDetail').textContent;
        expect(text).toContain('Cursor');
        expect(text).toContain('An AI-powered code editor.');
        expect(text).toContain('Code Generation');
        expect(text).toContain('35.0k');
    });

    it('renders each technology as its own chip', async () => {
        await boot();
        // Scope to the detail panel; the similar-agents grid has chips too.
        const chips = [...document.querySelectorAll('#agentDetail .tech-item')].map(c => c.textContent);
        expect(chips).toEqual(['Electron', 'GPT-4', 'VS Code']);
    });

    it('links to the external project safely', async () => {
        await boot();
        const link = document.querySelector('.agent-detail .view-btn');
        expect(link.href).toBe('https://cursor.sh/');
        expect(link.rel).toContain('noopener');
    });

    it('clears aria-busy when done', async () => {
        await boot();
        expect(document.getElementById('agentDetail').getAttribute('aria-busy')).toBe('false');
    });

    it('updates the breadcrumb and title', async () => {
        await boot();
        expect(document.getElementById('crumbName').textContent).toBe('Cursor');
        expect(document.title).toContain('Cursor');
    });
});

describe('escaping', () => {
    it('does not execute markup in agent fields', async () => {
        await boot('/agent/Evil', routes({
            '/api/agents/': { body: {
                name: 'Evil',
                metadata: { name: '<img src=x onerror="globalThis.pwned=1">', description: '<script>globalThis.pwned=1</script>', stack: '', category: 'X' },
            } },
        }));
        expect(document.querySelector('#agentDetail img')).toBeNull();
        expect(document.querySelector('#agentDetail script')).toBeNull();
        expect(globalThis.pwned).toBeUndefined();
    });

    it('rejects a javascript: url', async () => {
        await boot('/agent/Evil', routes({
            '/api/agents/': { body: {
                name: 'Evil',
                metadata: { name: 'Evil', description: 'd', stack: '', category: 'X', url: 'javascript:alert(1)' },
            } },
        }));
        expect(document.querySelector('.agent-detail .view-btn')).toBeNull();
    });
});

describe('similar agents', () => {
    it('shows other agents', async () => {
        await boot();
        expect(document.getElementById('similarSection').hidden).toBe(false);
        expect(document.querySelectorAll('#similarGrid .agent-card').length).toBeGreaterThan(0);
    });

    it('asks the dedicated endpoint, which excludes the agent itself', async () => {
        const calls = await boot();
        const call = calls.find(c => c.url.includes('/similar'));
        expect(call.url).toContain('/api/agents/Cursor/similar');

        const names = [...document.querySelectorAll('#similarGrid .agent-name')].map(n => n.textContent);
        expect(names).not.toContain('Cursor');
        expect(names).toContain('Aider');
    });

    it('stays hidden when nothing else is similar', async () => {
        await boot('/agent/Cursor', routes({
            '/similar': { body: { agents: [], metadata: { of: 'Cursor', count: 0 } } },
        }));
        expect(document.getElementById('similarSection').hidden).toBe(true);
    });

    it('does not break the page when the similar lookup fails', async () => {
        await boot('/agent/Cursor', routes({ '/similar': new Error('offline') }));
        expect(document.getElementById('agentDetail').textContent).toContain('Cursor');
        expect(document.getElementById('similarSection').hidden).toBe(true);
    });
});

describe('failure states', () => {
    it('reports an unknown agent', async () => {
        await boot('/agent/Nope', routes({
            '/api/agents/': { ok: false, status: 404, body: { error: 'no' } },
        }));
        expect(document.getElementById('agentDetail').textContent).toContain('Nope');
    });

    it('reports a server error', async () => {
        await boot('/agent/Cursor', routes({
            '/api/agents/': { ok: false, status: 500, body: {} },
        }));
        expect(document.getElementById('agentDetail').textContent).toContain('Could not load');
    });

    it('handles a path with no agent name', async () => {
        // Flask's <path:name> route would not match a bare /agent/, so this
        // guard only fires if the script is loaded somewhere unexpected.
        await boot('/');
        expect(document.getElementById('agentDetail').textContent).toContain('No agent specified');
    });
});

describe('the tech stack links onward', () => {
    it('makes each technology a link to its page', async () => {
        await boot();
        const chips = [...document.querySelectorAll('.tech-stack .tech-item')];

        expect(chips.length).toBeGreaterThan(0);
        expect(chips.every(c => c.tagName === 'A')).toBe(true);
    });

    it('escapes a technology whose name needs it', async () => {
        await boot();
        const hrefs = [...document.querySelectorAll('.tech-stack .tech-item')]
            .map(c => c.getAttribute('href'));

        expect(hrefs.every(h => h.startsWith('/tech/'))).toBe(true);
        expect(hrefs.every(h => !h.includes(' '))).toBe(true);
    });
});

describe('project health on the detail page', () => {
    it('shows a health row for an archived project', async () => {
        const archived = { ...CURSOR, metadata: { ...CURSOR.metadata, status: 'archived' } };
        await boot('/agent/Cursor', routes({ '/api/agents/': { body: archived } }));

        const labels = [...document.querySelectorAll('.detail-label')].map(l => l.textContent);
        expect(labels).toContain('Project health');
        expect(document.querySelector('.detail-row').parentElement.textContent)
            .toContain('Archived');
    });

    it('spells out dormancy', async () => {
        const dormant = { ...CURSOR, metadata: { ...CURSOR.metadata, status: 'dormant' } };
        await boot('/agent/Cursor', routes({ '/api/agents/': { body: dormant } }));

        expect(document.body.textContent).toContain('Not updated recently');
    });

    it('says nothing for a healthy one', async () => {
        /** A row reading "Active" on 217 of 236 pages is a row nobody reads. */
        await boot();
        const labels = [...document.querySelectorAll('.detail-label')].map(l => l.textContent);
        expect(labels).not.toContain('Project health');
    });
});

describe('where an archived project sends you', () => {
    /** The page a card's "Try instead" link lands on is the one most likely
     *  to need alternatives of its own — and it rendered the badge without
     *  them, leaving the dead end exactly where a reader goes for detail. */
    function withMeta(extra) {
        const agent = { name: 'Flowise', description: 'A visual builder.',
                        metadata: { name: 'Flowise', category: 'Framework',
                                    stack: 'TypeScript', stars: 1,
                                    description: 'A visual builder.',
                                    url: 'https://github.com/a/b', ...extra } };
        return routes({ '/api/agents/': { body: agent } });
    }

    it('lists them on an archived page', async () => {
        await boot('/agent/Flowise',
                   withMeta({ status: 'archived', alternatives: 'Langflow,Dify' }));
        const row = [...document.querySelectorAll('.detail-row')]
            .find(r => r.textContent.startsWith('Try instead'));

        expect([...row.querySelectorAll('a')].map(a => a.textContent))
            .toEqual(['Langflow', 'Dify']);
        expect(row.querySelector('a').getAttribute('href')).toBe('/agent/Langflow');
    });

    it('says nothing for a live project', async () => {
        await boot('/agent/Flowise', withMeta({ alternatives: 'Langflow' }));

        expect([...document.querySelectorAll('.detail-label')]
            .some(l => l.textContent === 'Try instead')).toBe(false);
    });

    it('says nothing when an archived page names none', async () => {
        await boot('/agent/Flowise', withMeta({ status: 'archived' }));

        expect([...document.querySelectorAll('.detail-label')]
            .some(l => l.textContent === 'Try instead')).toBe(false);
    });
});
