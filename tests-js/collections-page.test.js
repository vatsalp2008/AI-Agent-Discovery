import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { COLLECTIONS_HTML, bootPage, scriptsFor } from './helpers.js';

let C;

function boot() {
    bootPage({
        html: COLLECTIONS_HTML,
        script: 'collections-page.js',
        extraScripts: scriptsFor('collections.html', 'collections-page.js'),
    });
    C = globalThis.Collections;
}

function createVia(name) {
    document.getElementById('newCollectionName').value = name;
    document.getElementById('newCollectionForm').dispatchEvent(
        new window.Event('submit', { bubbles: true, cancelable: true }));
}

beforeEach(() => { localStorage.clear(); boot(); });
afterEach(() => localStorage.clear());

describe('empty state', () => {
    it('prompts when there are none', () => {
        expect(document.getElementById('collectionsArea').textContent).toContain('No collections yet');
    });
});

describe('creating', () => {
    it('creates and renders a collection', () => {
        createVia('Coding');
        expect(document.querySelectorAll('.collection-card')).toHaveLength(1);
        expect(document.querySelector('.collection-card h2').textContent).toBe('Coding (0)');
    });

    it('clears the input on success', () => {
        createVia('Coding');
        expect(document.getElementById('newCollectionName').value).toBe('');
    });

    it('shows why a create failed', () => {
        createVia('Coding');
        createVia('Coding');
        const error = document.getElementById('collectionsResult');
        expect(error.textContent).toContain('already exists');
    });

    it('does not submit the form normally', () => {
        const form = document.getElementById('newCollectionForm');
        const event = new window.Event('submit', { bubbles: true, cancelable: true });
        document.getElementById('newCollectionName').value = 'X';
        form.dispatchEvent(event);
        expect(event.defaultPrevented).toBe(true);
    });
});

describe('with agents', () => {
    beforeEach(() => {
        C.create('Coding');
        C.add('Coding', 'Aider');
        C.add('Coding', 'Cursor');
        boot();
    });

    it('lists the agents', () => {
        const names = [...document.querySelectorAll('.collection-agent a')].map(a => a.textContent);
        expect(names).toEqual(['Aider', 'Cursor']);
    });

    it('links each agent to its detail page', () => {
        expect(document.querySelector('.collection-agent a').getAttribute('href')).toBe('/agent/Aider');
    });

    it('offers a compare link', () => {
        const link = document.querySelector('.collection-card .compare-link');
        expect(decodeURIComponent(link.getAttribute('href'))).toBe('/compare?names=Aider,Cursor');
    });

    it('removing an agent updates the list', () => {
        document.querySelector('.collection-remove').click();
        const names = [...document.querySelectorAll('.collection-agent a')].map(a => a.textContent);
        expect(names).toEqual(['Cursor']);
    });

    it('deleting removes the collection', () => {
        document.querySelector('.collection-delete').click();
        expect(document.querySelectorAll('.collection-card')).toHaveLength(0);
    });

    it('shows the count in the heading', () => {
        expect(document.querySelector('.collection-card h2').textContent).toBe('Coding (2)');
    });
});

describe('a single-agent collection', () => {
    it('offers no compare link', () => {
        C.create('Solo');
        C.add('Solo', 'Aider');
        boot();
        expect(document.querySelector('.collection-card .compare-link')).toBeNull();
    });

    it('prompts an empty collection', () => {
        C.create('Empty');
        boot();
        expect(document.querySelector('.collection-card').textContent).toContain('Empty.');
    });
});

describe('escaping', () => {
    it('does not execute markup in a collection name', () => {
        C.create('<img src=x onerror="globalThis.pwned=1">');
        boot();
        expect(document.querySelector('#collectionsArea img')).toBeNull();
        expect(globalThis.pwned).toBeUndefined();
    });

    it('does not execute markup in an agent name', () => {
        C.create('X');
        C.add('X', '<script>globalThis.pwned=1</script>');
        boot();
        expect(document.querySelector('#collectionsArea script')).toBeNull();
        expect(globalThis.pwned).toBeUndefined();
    });
});

describe('export and import controls', () => {
    it('exports a downloadable file', () => {
        C.create('Coding');
        C.add('Coding', 'Aider');
        boot();

        const downloads = [];
        URL.createObjectURL = () => 'blob:fake';
        URL.revokeObjectURL = () => {};
        const realClick = HTMLAnchorElement.prototype.click;
        HTMLAnchorElement.prototype.click = function () { downloads.push(this.download); };

        try {
            document.getElementById('exportCollections').click();
            expect(downloads).toEqual(['agent-collections.json']);
            expect(document.getElementById('collectionsResult').textContent).toContain('Exported');
        } finally {
            HTMLAnchorElement.prototype.click = realClick;
        }
    });

    it('says so when there is nothing to export', () => {
        boot();
        document.getElementById('exportCollections').click();
        expect(document.getElementById('collectionsResult').textContent).toContain('nothing to export');
    });

    it('imports a file and re-renders', async () => {
        C.create('Coding');
        C.add('Coding', 'Aider');
        const backup = C.exportAll();
        localStorage.clear();
        boot();

        const input = document.getElementById('importCollections');
        Object.defineProperty(input, 'files', {
            value: [new window.File([backup], 'backup.json', { type: 'application/json' })],
            configurable: true,
        });
        input.dispatchEvent(new window.Event('change'));

        await new Promise(r => setTimeout(r, 50));
        expect(document.querySelector('.collection-card h2').textContent).toBe('Coding (1)');
        expect(document.getElementById('collectionsResult').textContent).toContain('1 new');
    });

    it('reports a malformed import', async () => {
        boot();
        const input = document.getElementById('importCollections');
        Object.defineProperty(input, 'files', {
            value: [new window.File(['{ not json'], 'bad.json')],
            configurable: true,
        });
        input.dispatchEvent(new window.Event('change'));

        await new Promise(r => setTimeout(r, 50));
        expect(document.getElementById('collectionsResult').textContent).toContain('valid JSON');
    });

    it('ignores a change event with no file', () => {
        boot();
        const input = document.getElementById('importCollections');
        Object.defineProperty(input, 'files', { value: [], configurable: true });
        expect(() => input.dispatchEvent(new window.Event('change'))).not.toThrow();
    });
});
