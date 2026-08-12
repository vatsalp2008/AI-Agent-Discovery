/**
 * Shared DOM helpers for the page scripts.
 *
 * Six pages each grew their own version of "replace this container with a
 * message", which drifted: some cleared `aria-busy`, some did not, and the
 * error styling was applied three different ways. Screen readers care about
 * that inconsistency, so it lives in one place now.
 *
 * Page-specific extras — clearing a footer, resetting a subtitle — stay in
 * the page, since folding them in here would just move the divergence.
 */
const UI = (() => {
    /** A message paragraph. Text is set via textContent, never innerHTML. */
    function messageElement(text, { error = false } = {}) {
        const p = document.createElement('p');
        p.className = error ? 'result-message error' : 'result-message';
        p.textContent = text;
        return p;
    }

    /**
     * Replace `container`'s contents with a message.
     *
     * Clears `aria-busy` by default: a container left busy after a failure
     * makes a screen reader wait for an update that never comes.
     */
    function showMessage(container, text, { error = false, clearBusy = true } = {}) {
        if (!container) return null;

        const element = messageElement(text, { error });
        container.replaceChildren(element);
        if (clearBusy && container.hasAttribute('aria-busy')) {
            container.setAttribute('aria-busy', 'false');
        }
        return element;
    }

    /** Convenience for the common failure case. */
    function showError(container, text, options = {}) {
        return showMessage(container, text, { ...options, error: true });
    }

    /** Set `aria-busy` on each element that has the attribute. */
    function setBusy(busy, ...containers) {
        containers.forEach(container => {
            if (container && container.hasAttribute('aria-busy')) {
                container.setAttribute('aria-busy', busy ? 'true' : 'false');
            }
        });
    }

    return { messageElement, showMessage, showError, setBusy };
})();

if (typeof module !== 'undefined') module.exports = UI;
