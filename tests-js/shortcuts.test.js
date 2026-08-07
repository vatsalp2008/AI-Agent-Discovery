import { beforeEach, describe, expect, it } from 'vitest';

import { bootPage } from './helpers.js';

const HTML = `
    <input id="searchInput" type="search" value="hello">
    <textarea id="notes"></textarea>
    <div class="help-dialog" id="shortcutHelp" hidden>
      <button type="button" class="help-close">Close</button>
    </div>
`;

let Shortcuts;

function press(key, target = document.body, extra = {}) {
    const event = new window.KeyboardEvent('keydown', { key, bubbles: true, cancelable: true, ...extra });
    target.dispatchEvent(event);
    return event;
}

beforeEach(() => {
    bootPage({ html: HTML, script: 'shortcuts.js' });
    Shortcuts = globalThis.Shortcuts;
});

describe('focusing search', () => {
    it('/ focuses and selects the search box', () => {
        const event = press('/');
        expect(document.activeElement.id).toBe('searchInput');
        expect(event.defaultPrevented).toBe(true);  // not the browser quick-find
    });

    it('s also focuses search', () => {
        press('s');
        expect(document.activeElement.id).toBe('searchInput');
    });

    it('falls back to the dashboard filter box', () => {
        bootPage({ html: '<input id="filterQuery">', script: 'shortcuts.js' });
        press('s');
        expect(document.activeElement.id).toBe('filterQuery');
    });
});

describe('not stealing keys while typing', () => {
    it('ignores s typed into the search box', () => {
        const input = document.getElementById('searchInput');
        const event = press('s', input);
        expect(event.defaultPrevented).toBe(false);
    });

    it('ignores / typed into a textarea', () => {
        const event = press('/', document.getElementById('notes'));
        expect(event.defaultPrevented).toBe(false);
    });

    it('ignores keys in contenteditable regions', () => {
        const div = document.createElement('div');
        div.contentEditable = 'true';
        Object.defineProperty(div, 'isContentEditable', { value: true });
        document.body.appendChild(div);
        expect(press('?', div).defaultPrevented).toBe(false);
    });

    it('ignores shortcuts held with a modifier', () => {
        expect(press('s', document.body, { metaKey: true }).defaultPrevented).toBe(false);
        expect(press('/', document.body, { ctrlKey: true }).defaultPrevented).toBe(false);
    });
});

describe('the help dialog', () => {
    it('? opens it', () => {
        press('?');
        expect(document.getElementById('shortcutHelp').hidden).toBe(false);
    });

    it('? closes it again', () => {
        press('?');
        press('?');
        expect(document.getElementById('shortcutHelp').hidden).toBe(true);
    });

    it('moves focus to the close button when opened', () => {
        press('?');
        expect(document.activeElement.className).toBe('help-close');
    });

    it('Escape closes it', () => {
        press('?');
        press('Escape');
        expect(document.getElementById('shortcutHelp').hidden).toBe(true);
    });

    it('the close button works', () => {
        press('?');
        document.querySelector('.help-close').click();
        expect(document.getElementById('shortcutHelp').hidden).toBe(true);
    });
});

describe('Escape', () => {
    it('blurs the search box', () => {
        const input = document.getElementById('searchInput');
        input.focus();
        press('Escape', input);
        expect(document.activeElement).not.toBe(input);
    });

    it('closing help takes priority over blurring', () => {
        press('?');
        const input = document.getElementById('searchInput');
        input.focus();
        press('Escape', input);
        expect(document.getElementById('shortcutHelp').hidden).toBe(true);
    });
});

describe('pages without the markup', () => {
    it('does not throw when there is no search box or dialog', () => {
        bootPage({ html: '<p>nothing here</p>', script: 'shortcuts.js' });
        expect(() => { press('/'); press('?'); press('Escape'); }).not.toThrow();
    });
});
