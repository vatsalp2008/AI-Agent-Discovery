/**
 * Light/dark theme switching.
 *
 * The saved choice is applied by an inline-free early script (see base.html)
 * before first paint, so there is no flash of the wrong theme. With no saved
 * choice the CSS `prefers-color-scheme` rule decides, and this file only
 * records an explicit override.
 */
const Theme = (() => {
    const STORAGE_KEY = 'agentdiscovery:theme';

    function stored() {
        try {
            const value = localStorage.getItem(STORAGE_KEY);
            return value === 'light' || value === 'dark' ? value : null;
        } catch (error) {
            return null;  // private mode, or storage disabled
        }
    }

    function systemPrefersLight() {
        return typeof window.matchMedia === 'function'
            && window.matchMedia('(prefers-color-scheme: light)').matches;
    }

    /** The theme actually in effect, saved or inherited from the OS. */
    function current() {
        return document.documentElement.getAttribute('data-theme')
            || stored()
            || (systemPrefersLight() ? 'light' : 'dark');
    }

    function apply(theme) {
        document.documentElement.setAttribute('data-theme', theme);
        try {
            localStorage.setItem(STORAGE_KEY, theme);
        } catch (error) {
            // Not fatal: the theme still applies for this page view.
        }
    }

    function toggle() {
        const next = current() === 'dark' ? 'light' : 'dark';
        apply(next);
        return next;
    }

    /** Restore a saved choice. Called before paint, and again on load. */
    function restore() {
        const saved = stored();
        if (saved) document.documentElement.setAttribute('data-theme', saved);
        return saved;
    }

    function label(theme) {
        return theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme';
    }

    function icon(theme) {
        return theme === 'dark' ? '☀' : '☾';
    }

    return { STORAGE_KEY, current, apply, toggle, restore, label, icon };
})();

// Applied immediately, not on DOMContentLoaded: base.html loads this file in
// <head> without `defer`, so the attribute is set before first paint and the
// page never flashes the wrong theme. Doing this with an inline script would
// require loosening the Content-Security-Policy.
Theme.restore();

document.addEventListener('DOMContentLoaded', () => {
    const button = document.getElementById('themeToggle');
    if (!button) return;

    function paint(theme) {
        button.textContent = Theme.icon(theme);
        button.setAttribute('aria-label', Theme.label(theme));
        button.title = Theme.label(theme);
    }

    paint(Theme.current());
    button.addEventListener('click', () => paint(Theme.toggle()));
});

if (typeof module !== 'undefined') module.exports = Theme;
