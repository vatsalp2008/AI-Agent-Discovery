/**
 * Global keyboard shortcuts.
 *
 *   /  or  s   focus the search box
 *   ?          toggle the shortcut help
 *   Esc        close help, or blur the search box
 *
 * Every shortcut is a single unmodified key, so each handler first checks the
 * event did not originate in a field the user is typing into — otherwise
 * typing "s" in the search box would be swallowed.
 */
const Shortcuts = (() => {
    const TYPING_TAGS = new Set(['INPUT', 'TEXTAREA', 'SELECT']);

    /** True when the key belongs to whatever the user is editing. */
    function isTyping(target) {
        if (!target) return false;
        if (TYPING_TAGS.has(target.tagName)) return true;
        return Boolean(target.isContentEditable);
    }

    /** True when a modifier is held, meaning it is a browser/OS shortcut. */
    function hasModifier(event) {
        return event.ctrlKey || event.metaKey || event.altKey;
    }

    function focusSearch() {
        const input = document.getElementById('searchInput')
            || document.getElementById('filterQuery');
        if (!input) return false;
        input.focus();
        input.select();
        return true;
    }

    function helpDialog() {
        return document.getElementById('shortcutHelp');
    }

    function toggleHelp(force) {
        const dialog = helpDialog();
        if (!dialog) return false;
        const show = force === undefined ? dialog.hidden : force;
        dialog.hidden = !show;
        if (show) {
            const close = dialog.querySelector('.help-close');
            if (close) close.focus();
        }
        return true;
    }

    function handle(event) {
        if (hasModifier(event)) return false;

        if (event.key === 'Escape') {
            const dialog = helpDialog();
            if (dialog && !dialog.hidden) {
                toggleHelp(false);
                return true;
            }
            if (isTyping(event.target) && event.target.blur) {
                event.target.blur();
                return true;
            }
            return false;
        }

        // Remaining shortcuts are plain letters, so ignore them while typing.
        if (isTyping(event.target)) return false;

        if (event.key === '/' || event.key === 's') {
            // Prevent "/" opening the browser's own quick-find.
            if (focusSearch()) {
                event.preventDefault();
                return true;
            }
            return false;
        }

        if (event.key === '?') {
            if (toggleHelp()) {
                event.preventDefault();
                return true;
            }
        }

        return false;
    }

    function install(target) {
        (target || document).addEventListener('keydown', handle);
    }

    return { isTyping, hasModifier, handle, install, toggleHelp, focusSearch };
})();

document.addEventListener('DOMContentLoaded', () => {
    Shortcuts.install(document);

    const dialog = document.getElementById('shortcutHelp');
    if (dialog) {
        const close = dialog.querySelector('.help-close');
        if (close) close.addEventListener('click', () => Shortcuts.toggleHelp(false));
    }
});

if (typeof module !== 'undefined') module.exports = Shortcuts;
