import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { bootPage } from './helpers.js';

let Theme;

const TOGGLE_HTML = '<button id="themeToggle" class="theme-toggle"></button>';

// bootPage rather than loadScript: it captures the page's DOMContentLoaded
// handler instead of registering it, so handlers do not accumulate on the
// shared jsdom document and stack up click listeners on the button.
function boot(html = TOGGLE_HTML) {
    document.documentElement.removeAttribute('data-theme');
    bootPage({ html, script: 'theme.js' });
    Theme = globalThis.Theme;
    return Theme;
}

beforeEach(() => {
    localStorage.clear();
    // Default to a dark OS preference unless a test says otherwise.
    window.matchMedia = (q) => ({ matches: false, media: q });
});

afterEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute('data-theme');
});

describe('choosing a theme', () => {
    it('follows the OS when nothing is saved', () => {
        window.matchMedia = (q) => ({ matches: q.includes('light'), media: q });
        boot();
        expect(Theme.current()).toBe('light');
        expect(document.documentElement.hasAttribute('data-theme')).toBe(false);
    });

    it('falls back to dark without matchMedia', () => {
        delete window.matchMedia;
        boot();
        expect(Theme.current()).toBe('dark');
    });

    it('restores a saved choice before paint', () => {
        localStorage.setItem('agentdiscovery:theme', 'light');
        boot();
        expect(document.documentElement.getAttribute('data-theme')).toBe('light');
    });

    it('a saved choice overrides the OS preference', () => {
        window.matchMedia = (q) => ({ matches: q.includes('light'), media: q });
        localStorage.setItem('agentdiscovery:theme', 'dark');
        boot();
        expect(Theme.current()).toBe('dark');
    });

    it('ignores a corrupt stored value', () => {
        localStorage.setItem('agentdiscovery:theme', 'neon');
        boot();
        expect(document.documentElement.hasAttribute('data-theme')).toBe(false);
        expect(Theme.current()).toBe('dark');
    });
});

describe('toggling', () => {
    it('switches dark to light and back', () => {
        boot();
        expect(Theme.toggle()).toBe('light');
        expect(document.documentElement.getAttribute('data-theme')).toBe('light');
        expect(Theme.toggle()).toBe('dark');
    });

    it('persists the choice', () => {
        boot();
        Theme.toggle();
        expect(localStorage.getItem('agentdiscovery:theme')).toBe('light');
    });

    it('survives storage being unavailable', () => {
        boot();
        const real = Storage.prototype.setItem;
        Storage.prototype.setItem = () => { throw new Error('denied'); };
        try {
            expect(() => Theme.toggle()).not.toThrow();
            expect(document.documentElement.getAttribute('data-theme')).toBe('light');
        } finally {
            Storage.prototype.setItem = real;
        }
    });
});

describe('the toggle button', () => {
    it('is labelled for assistive tech', () => {
        boot();
        const button = document.getElementById('themeToggle');
        expect(button.getAttribute('aria-label')).toContain('light');
    });

    it('updates its label and icon when clicked', () => {
        boot();
        const button = document.getElementById('themeToggle');
        const before = button.textContent;
        button.click();
        expect(button.textContent).not.toBe(before);
        expect(button.getAttribute('aria-label')).toContain('dark');
    });

    it('clicking twice returns to the start', () => {
        boot();
        const button = document.getElementById('themeToggle');
        const before = button.textContent;
        button.click();
        button.click();
        expect(button.textContent).toBe(before);
    });

    it('does not break on a page with no toggle', () => {
        expect(() => boot('')).not.toThrow();
    });
});
