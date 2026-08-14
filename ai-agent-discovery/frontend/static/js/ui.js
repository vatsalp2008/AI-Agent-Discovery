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

        // An empty message means "nothing to report", so the region is
        // emptied rather than given a blank paragraph. Callers written
        // against the older two-paragraph pattern pass '' to clear, and
        // would otherwise leave a stray empty <p> in a live region.
        if (!text) {
            container.replaceChildren();
            if (clearBusy && container.hasAttribute('aria-busy')) {
                container.setAttribute('aria-busy', 'false');
            }
            return null;
        }

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

    /**
     * A `say(message, isError)` bound to one container.
     *
     * Four page scripts had grown the same three-line wrapper around
     * showMessage. Binding the container once is what each of them actually
     * wanted, and it keeps the error flag spelled the same way everywhere.
     */
    function reporter(container) {
        return (message, isError) =>
            showMessage(container, message, { error: Boolean(isError) });
    }

    /**
     * Offer `text` to the browser as a file download.
     *
     * Lived in export-results.js and collections-page.js in near-identical
     * copies; the saved-searches page would have made three. The revoke is
     * deferred because doing it immediately cancels the download in some
     * browsers, which is the sort of detail worth having in one place.
     */
    function download(text, filename, mime = 'application/json') {
        const url = URL.createObjectURL(new Blob([text], { type: mime }));
        const link = document.createElement('a');
        link.href = url;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        link.remove();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
    }

    /** Set `aria-busy` on each element that has the attribute. */
    function setBusy(busy, ...containers) {
        containers.forEach(container => {
            if (container && container.hasAttribute('aria-busy')) {
                container.setAttribute('aria-busy', busy ? 'true' : 'false');
            }
        });
    }

    return { messageElement, showMessage, showError, setBusy, reporter, download };
})();

if (typeof module !== 'undefined') module.exports = UI;
