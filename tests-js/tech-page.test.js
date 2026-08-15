import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { TECH_HTML, bootPage, flush, makeAgent, scriptsFor, stubFetch } from './helpers.js';

function agents(...names) {
    return names.map(name => makeAgent({
        name,
        metadata: { name, category: 'Framework', stack: 'Python,PyTorch', stars: 100,
                    description: `${name} does things.`, url: 'https://example.com' },
    }));
}

function routes(overrides = {}) {
    return {
        '/api/tech': { body: [{ name: 'Python', count: 171 }, { name: 'PyTorch', count: 36 }] },
        '/api/agents?': { body: { agents: agents('Ollama', 'vLLM'), metadata: { total: 171 } } },
        ...overrides,
    };
}

async function boot(path = '/tech/Python', r = routes()) {
    window.history.replaceState({}, '', path);
    const calls = stubFetch(r);
    bootPage({ html: TECH_HTML, script: 'tech.js',
               extraScripts: scriptsFor('tech.html', 'tech.js') });
    await flush();
    return calls;
}

beforeEach(() => { localStorage.clear(); window.history.replaceState({}, '', '/tech/Python'); });
afterEach(() => { delete globalThis.fetch; });

describe('listing what uses a technology', () => {
    it('asks the API for that technology', async () => {
        const calls = await boot();
        const call = calls.find(c => c.url.includes('/api/agents'));
        expect(decodeURIComponent(call.url)).toContain('tech=Python');
    });

    it('renders a card per agent', async () => {
        await boot();
        expect(document.querySelectorAll('#techGrid .agent-card')).toHaveLength(2);
    });

    it('reports the whole total, not just the page', async () => {
        await boot();
        expect(document.getElementById('techCount').textContent).toContain('171');
    });

    it('clears the busy flag once loaded', async () => {
        await boot();
        expect(document.getElementById('techGrid').getAttribute('aria-busy')).toBe('false');
    });

    it('reads a name that needed escaping', async () => {
        /** URLSearchParams writes the space as "+", which is what a query
         *  string means by it — Flask decodes it back to a space. */
        const calls = await boot('/tech/ROS%202');
        const call = calls.find(c => c.url.includes('/api/agents'));

        const sent = new URL(call.url, 'http://x').searchParams.get('tech');
        expect(sent).toBe('ROS 2');
    });

    it('survives a malformed escape rather than sticking on Loading', async () => {
        /** decodeURIComponent throws on /tech/100%, which would otherwise
         *  kill the handler and leave the header saying "Loading…". */
        await boot('/tech/100%');
        expect(document.getElementById('techCount').textContent).not.toBe('Loading…');
    });
});

describe('when there is nothing to show', () => {
    it('says so, naming the technology', async () => {
        await boot('/tech/Fortran', routes({
            '/api/agents?': { body: { agents: [], metadata: { total: 0 } } },
        }));
        expect(document.getElementById('techGrid').textContent).toContain('Fortran');
    });

    it('still offers other technologies to browse', async () => {
        await boot('/tech/Fortran', routes({
            '/api/agents?': { body: { agents: [], metadata: { total: 0 } } },
        }));
        expect(document.querySelectorAll('#techOther a').length).toBeGreaterThan(0);
    });
});

describe('browsing on', () => {
    it('links to the other technologies', async () => {
        await boot();
        const links = [...document.querySelectorAll('#techOther a')].map(a => a.textContent);
        expect(links).toContain('PyTorch (36)');
    });

    it('does not link back to the one being viewed', async () => {
        await boot();
        const links = [...document.querySelectorAll('#techOther a')].map(a => a.textContent);
        expect(links.some(t => t.startsWith('Python '))).toBe(false);
    });

    it('caps the list rather than printing every technology', async () => {
        /** The catalogue has well over a hundred; a wall of them is not
         *  navigation. */
        const many = Array.from({ length: 120 }, (_, i) => ({ name: `T${i}`, count: 1 }));
        await boot('/tech/Python', routes({ '/api/tech': { body: many } }));

        expect(document.querySelectorAll('#techOther a').length).toBeLessThanOrEqual(24);
    });
});

describe('when the API fails', () => {
    it('says so instead of leaving the page loading', async () => {
        await boot('/tech/Python', routes({
            '/api/agents?': { ok: false, status: 500, body: {} },
        }));

        expect(document.getElementById('techGrid').textContent).toContain('Could not load');
        expect(document.getElementById('techCount').textContent).not.toBe('Loading…');
    });
});
