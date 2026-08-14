/**
 * The test helpers are shared by every page suite, so a mistake here is a
 * mistake in all of them. These are cheap checks on the contract they offer.
 */
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import { scriptsFor, stubFetch } from './helpers.js';

const SOURCE = readFileSync(
    resolve(dirname(fileURLToPath(import.meta.url)), 'helpers.js'), 'utf8');

describe('the helper module documents itself', () => {
    it('has no JSDoc block stranded above another', () => {
        /** Inserting an export above an existing one leaves its comment
         *  describing the wrong thing — which happened three times in one
         *  change, and reads as correct until someone follows it. */
        expect(SOURCE.match(/\*\/\s*\n\/\*\*/g)).toBeNull();
    });

    it('comments every exported helper', () => {
        const undocumented = [...SOURCE.matchAll(
            /\n(?<!\*\/\n)export (?:const|function|async function) (\w+)/g)].map(m => m[1]);
        expect(undocumented).toEqual([]);
    });
});

describe('scriptsFor reads the real template', () => {
    it('lists what the page loads, minus the page script itself', () => {
        const files = scriptsFor('saved.html', 'saved-page.js').map(s => s.file);
        expect(files).toContain('saved-searches.js');
        expect(files).not.toContain('saved-page.js');
    });

    it('names the global each file actually declares', () => {
        const entry = scriptsFor('saved.html', 'saved-page.js')
            .find(s => s.file === 'saved-searches.js');
        expect(entry.global).toBe('SavedSearches');
    });
});

describe('the fetch stub enforces the method', () => {
    it('serves a matching method', async () => {
        stubFetch({ 'POST /api/search': { body: { ok: 1 } } });
        const response = await fetch('/api/search', { method: 'POST' });
        expect(await response.json()).toEqual({ ok: 1 });
        delete globalThis.fetch;
    });

    it('refuses a mismatched one, the way a 405 would', async () => {
        /** Without this, /saved shipped calling POST-only /api/search with a
         *  GET and every test passed. */
        stubFetch({ 'POST /api/search': { body: {} } });
        await expect(fetch('/api/search')).rejects.toThrow(/unrouted/);
        delete globalThis.fetch;
    });

    it('still matches a key with no method, for the GET endpoints', async () => {
        stubFetch({ '/api/agents': { body: [] } });
        expect((await fetch('/api/agents')).ok).toBe(true);
        delete globalThis.fetch;
    });
});
