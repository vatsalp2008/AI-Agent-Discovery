/** The combobox wiring, independent of the search page. */

import { beforeEach, describe, expect, it } from 'vitest';

import { bootPage } from './helpers.js';

const HTML = `
    <input id="input" type="search" role="combobox" aria-expanded="false">
    <ul id="list" role="listbox" hidden></ul>
`;

const NAMES = [{ name: 'ComfyUI' }, { name: 'Cursor' }, { name: 'Vocode' }];

let attached;
let chosen;

function input() { return document.getElementById('input'); }
function list() { return document.getElementById('list'); }

function type(value) {
    input().value = value;
    input().dispatchEvent(new window.Event('input'));
}

function press(key) {
    const event = new window.KeyboardEvent('keydown', { key, bubbles: true, cancelable: true });
    input().dispatchEvent(event);
    return event;
}

beforeEach(async () => {
    bootPage({
        html: HTML,
        script: 'search-suggestions.js',
        extraScripts: [{ file: 'suggest.js', global: 'Suggest' }],
    });
    chosen = [];
    attached = globalThis.SearchSuggestions.attach({
        input: input(),
        list: list(),
        onChoose: (name) => chosen.push(name),
        fetchNames: async () => NAMES,
    });
    await attached.load();
});

describe('showing matches', () => {
    it('lists matching names', () => {
        type('cu');
        expect([...list().querySelectorAll('.suggestion')].map(i => i.textContent)).toEqual(['Cursor']);
        expect(attached.isOpen()).toBe(true);
    });

    it('highlights the matched span', () => {
        type('urs');
        expect(list().querySelector('mark').textContent).toBe('urs');
    });

    it('closes when nothing matches', () => {
        type('zzzz');
        expect(attached.isOpen()).toBe(false);
    });
});

describe('keyboard', () => {
    it('moves down through the list', () => {
        type('c');   // ComfyUI, Cursor, Vocode
        press('ArrowDown');
        expect(list().children[0].classList.contains('active')).toBe(true);
        press('ArrowDown');
        expect(list().children[1].classList.contains('active')).toBe(true);
    });

    it('wraps from the first item back to the last', () => {
        type('c');
        press('ArrowDown');                      // index 0
        press('ArrowUp');                        // wraps to the end
        expect(list().children[2].classList.contains('active')).toBe(true);
    });

    it('wraps from the last item back to the first', () => {
        type('c');
        press('ArrowUp');                        // opens at the end
        press('ArrowDown');                      // wraps to the start
        expect(list().children[0].classList.contains('active')).toBe(true);
    });

    it('Enter chooses the highlighted name', () => {
        type('c');
        press('ArrowDown');
        press('Enter');
        expect(chosen).toEqual(['ComfyUI']);
        expect(input().value).toBe('ComfyUI');
    });

    it('Enter with nothing highlighted does not choose', () => {
        type('c');
        expect(press('Enter').defaultPrevented).toBe(false);
        expect(chosen).toEqual([]);
    });

    it('Escape closes without choosing', () => {
        type('c');
        press('Escape');
        expect(attached.isOpen()).toBe(false);
        expect(chosen).toEqual([]);
    });

    it('ignores keys when closed', () => {
        expect(press('ArrowDown').defaultPrevented).toBe(false);
    });
});

describe('ARIA state', () => {
    it('tracks expanded and the active descendant', () => {
        expect(input().getAttribute('aria-expanded')).toBe('false');
        type('c');
        expect(input().getAttribute('aria-expanded')).toBe('true');

        press('ArrowDown');
        expect(input().getAttribute('aria-activedescendant')).toBe('suggestion-0');

        attached.close();
        expect(input().getAttribute('aria-expanded')).toBe('false');
        expect(input().hasAttribute('aria-activedescendant')).toBe(false);
    });

    it('marks the selected option', () => {
        type('c');
        press('ArrowDown');
        expect(list().children[0].getAttribute('aria-selected')).toBe('true');
        expect(list().children[1].getAttribute('aria-selected')).toBe('false');
    });
});

describe('mouse', () => {
    it('mousedown chooses, so blur cannot close first', () => {
        type('cu');
        list().querySelector('.suggestion').dispatchEvent(
            new window.MouseEvent('mousedown', { bubbles: true, cancelable: true }));
        expect(chosen).toEqual(['Cursor']);
    });
});

describe('a page without the markup', () => {
    it('returns a no-op handle rather than throwing', async () => {
        const handle = globalThis.SearchSuggestions.attach({ input: null, list: null });
        expect(() => handle.close()).not.toThrow();
        await expect(handle.load()).resolves.toBeUndefined();
        expect(handle.isOpen()).toBe(false);
    });
});
