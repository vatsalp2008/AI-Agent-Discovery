import { beforeAll, beforeEach, describe, expect, it } from 'vitest';

import { loadScript } from './helpers.js';

let UI;

beforeAll(() => { UI = loadScript('ui.js', 'UI'); });
beforeEach(() => { document.body.innerHTML = '<div id="box" aria-busy="true"></div>'; });

const box = () => document.getElementById('box');

describe('messages', () => {
    it('builds a plain message', () => {
        const el = UI.messageElement('hello');
        expect(el.tagName).toBe('P');
        expect(el.className).toBe('result-message');
        expect(el.textContent).toBe('hello');
    });

    it('builds an error message', () => {
        expect(UI.messageElement('bad', { error: true }).className).toBe('result-message error');
    });

    it('never interprets text as markup', () => {
        const el = UI.messageElement('<img src=x onerror="globalThis.pwned=1">');
        expect(el.querySelector('img')).toBeNull();
        expect(globalThis.pwned).toBeUndefined();
    });

    it('replaces the container contents', () => {
        box().innerHTML = '<span>old</span>';
        UI.showMessage(box(), 'new');
        expect(box().textContent).toBe('new');
        expect(box().querySelector('span')).toBeNull();
    });

    it('clears aria-busy so a reader is not left waiting', () => {
        UI.showMessage(box(), 'done');
        expect(box().getAttribute('aria-busy')).toBe('false');
    });

    it('can leave aria-busy alone', () => {
        UI.showMessage(box(), 'still working', { clearBusy: false });
        expect(box().getAttribute('aria-busy')).toBe('true');
    });

    it('does not add aria-busy to a container without it', () => {
        document.body.innerHTML = '<div id="plain"></div>';
        const plain = document.getElementById('plain');
        UI.showMessage(plain, 'x');
        expect(plain.hasAttribute('aria-busy')).toBe(false);
    });

    it('showError marks it as an error', () => {
        expect(UI.showError(box(), 'oops').className).toBe('result-message error');
    });

    it('tolerates a missing container', () => {
        expect(UI.showMessage(null, 'x')).toBeNull();
        expect(UI.showError(undefined, 'x')).toBeNull();
    });
});

describe('setBusy', () => {
    it('sets and clears the flag', () => {
        UI.setBusy(true, box());
        expect(box().getAttribute('aria-busy')).toBe('true');
        UI.setBusy(false, box());
        expect(box().getAttribute('aria-busy')).toBe('false');
    });

    it('skips containers without the attribute', () => {
        document.body.innerHTML = '<div id="plain"></div>';
        const plain = document.getElementById('plain');
        UI.setBusy(true, plain);
        expect(plain.hasAttribute('aria-busy')).toBe(false);
    });

    it('ignores nulls', () => {
        expect(() => UI.setBusy(false, null, undefined, box())).not.toThrow();
    });
});

describe('an empty message', () => {
    it('empties the region instead of adding a blank paragraph', () => {
        const container = document.createElement('div');
        UI.showMessage(container, 'something went wrong', { error: true });
        expect(container.children).toHaveLength(1);

        UI.showMessage(container, '');
        expect(container.children).toHaveLength(0);
        expect(container.textContent).toBe('');
    });

    it('returns null, since there is no element to hand back', () => {
        expect(UI.showMessage(document.createElement('div'), '')).toBeNull();
    });

    it('still clears aria-busy', () => {
        /** A region left busy makes a screen reader wait for an update that
         *  never comes — true whether or not there is a message. */
        const container = document.createElement('div');
        container.setAttribute('aria-busy', 'true');
        UI.showMessage(container, '');
        expect(container.getAttribute('aria-busy')).toBe('false');
    });

    it('treats undefined the same way', () => {
        const container = document.createElement('div');
        UI.showError(container, undefined);
        expect(container.children).toHaveLength(0);
    });
});
