import { afterEach, beforeAll, describe, expect, it } from 'vitest';

import { flush, loadScript, stubFetch } from './helpers.js';

let Banner;

beforeAll(() => { Banner = loadScript('setup-banner.js', 'SetupBanner'); });
afterEach(() => { delete globalThis.fetch; });

describe('deciding what to say', () => {
    it('says nothing when the index is healthy', () => {
        expect(Banner.message({ status: 'ok', indexed_agents: 106 })).toBeNull();
    });

    it('reports an empty index as missing, not merely stale', () => {
        // Both flags set: the index has no vectors AND the catalogue moved on.
        // "Out of date" would understate it — searches return nothing at all.
        const info = Banner.message({ status: 'degraded', indexed_agents: 0, catalogue_stale: true });
        expect(info.title).toContain('No agents are indexed');
    });

    it('does not suggest seeding when the store could not be loaded', () => {
        // Ollama unreachable: `make seed` fails the same way.
        const info = Banner.message({ status: 'error', indexed_agents: 0, detail: 'connection refused' });
        expect(info.title).toContain('could not be loaded');
        expect(info.detail).toContain('connection refused');
        expect(info.command).toBe('make doctor');
    });

    it('passes the server own detail through', () => {
        const info = Banner.message({ status: 'degraded', indexed_agents: 0, detail: 'Run seed.py to populate it.' });
        expect(info.detail).toBe('Run seed.py to populate it.');
    });

    it('explains an unseeded index', () => {
        const info = Banner.message({ status: 'degraded', indexed_agents: 0, detail: 'No agents indexed. Run seed.py...' });
        expect(info.title).toContain('No agents are indexed');
        expect(info.command).toBe('make seed');
    });

    it('explains a stale catalogue on an otherwise healthy index', () => {
        const info = Banner.message({ status: 'ok', indexed_agents: 128, catalogue_stale: true });
        expect(info.title).toContain('out of date');
    });

    it('explains an embedding model mismatch', () => {
        const info = Banner.message({
            status: 'degraded',
            detail: "Index was built with embedding model 'llama3.2' but ...",
        });
        expect(info.title).toContain('different embedding model');
        expect(info.detail).toContain('llama3.2');
    });

    it('says nothing for a missing payload', () => {
        expect(Banner.message(null)).toBeNull();
    });
});

describe('rendering', () => {
    it('shows the title, detail and command', () => {
        const el = Banner.render({ title: 'T', detail: 'D', command: 'make seed' });
        expect(el.querySelector('strong').textContent).toBe('T');
        expect(el.querySelector('.setup-banner-detail').textContent).toBe('D');
        expect(el.querySelector('.setup-banner-command').textContent).toBe('make seed');
        expect(el.getAttribute('role')).toBe('status');
    });

    it('escapes anything the server sent', () => {
        const el = Banner.render({
            title: '<img src=x onerror="globalThis.pwned=1">', detail: 'd', command: 'c',
        });
        expect(el.querySelector('img')).toBeNull();
        expect(globalThis.pwned).toBeUndefined();
    });
});

describe('checking on load', () => {
    it('prepends a banner when the index is unusable', async () => {
        document.body.innerHTML = '<div class="container"><p>page</p></div>';
        stubFetch({ '/api/health': { ok: false, status: 503, body: { status: 'degraded', detail: 'No agents indexed.' } } });

        await Banner.check(document.querySelector('.container'));
        const banner = document.querySelector('.setup-banner');
        expect(banner).not.toBeNull();
        expect(document.querySelector('.container').firstChild).toBe(banner);
    });

    it('adds nothing when healthy', async () => {
        document.body.innerHTML = '<div class="container"></div>';
        stubFetch({ '/api/health': { body: { status: 'ok' } } });

        await Banner.check(document.querySelector('.container'));
        expect(document.querySelector('.setup-banner')).toBeNull();
    });

    it('stays quiet when health cannot be reached', async () => {
        document.body.innerHTML = '<div class="container"></div>';
        stubFetch({ '/api/health': new Error('offline') });

        await expect(Banner.check(document.querySelector('.container'))).resolves.toBeNull();
        expect(document.querySelector('.setup-banner')).toBeNull();
    });

    it('does nothing without a container', async () => {
        await expect(Banner.check(null)).resolves.toBeNull();
    });
});
