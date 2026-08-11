/**
 * A banner explaining an unusable index, shown on every page.
 *
 * Without it a fresh checkout looks broken rather than unconfigured: search
 * reports "no agents found", the dashboard shows zeroes, and nothing says the
 * index simply has not been built. /api/health already distinguishes those
 * cases, so this surfaces what it says.
 */
const SetupBanner = (() => {
    /**
     * What to tell the user, given a health payload. Returns null when the
     * index is fine — the common case, where nothing should be shown.
     */
    function message(health) {
        if (!health) return null;

        // Order matters. An unusable index is checked first: a stale catalogue
        // is only a warning (searches still work, they return the previous
        // contents), but an empty or mismatched index means they return
        // nothing at all. Reporting the milder problem first would tell
        // someone their index is "out of date" when it is not there.
        const unusable = health.status !== 'ok' || health.indexed_agents === 0;

        if (unusable) {
            if (health.detail && health.detail.includes('embedding model')) {
                return {
                    title: 'The index was built with a different embedding model.',
                    detail: health.detail,
                    command: 'make seed',
                };
            }

            // The store threw — Ollama unreachable, most likely. Seeding would
            // fail the same way, so do not offer it as the remedy.
            if (health.status === 'error') {
                return {
                    title: 'The search index could not be loaded.',
                    detail: health.detail || 'The server could not open the index.',
                    command: 'make doctor',
                };
            }

            return {
                title: 'No agents are indexed yet.',
                detail: health.detail
                    || 'The search index has not been built, so every search will come back empty.',
                command: 'make seed',
            };
        }

        if (health.catalogue_stale) {
            return {
                title: 'The index is out of date.',
                detail: 'data/agents.json has changed since it was built.',
                command: 'make seed',
            };
        }

        return null;
    }

    function render(info) {
        const banner = document.createElement('div');
        banner.className = 'setup-banner';
        banner.setAttribute('role', 'status');

        const title = document.createElement('strong');
        title.textContent = info.title;
        banner.appendChild(title);

        const detail = document.createElement('span');
        detail.className = 'setup-banner-detail';
        detail.textContent = info.detail;
        banner.appendChild(detail);

        const command = document.createElement('code');
        command.className = 'setup-banner-command';
        command.textContent = info.command;
        banner.appendChild(command);

        return banner;
    }

    async function check(container) {
        if (!container) return null;
        try {
            const response = await fetch('/api/health');
            // 503 is expected here; the body is what matters.
            const health = await response.json();

            const info = message(health);
            if (!info) return null;

            container.prepend(render(info));
            return info;
        } catch (error) {
            console.error('Could not check setup status:', error);
            return null;
        }
    }

    return { message, render, check };
})();

document.addEventListener('DOMContentLoaded', () => {
    SetupBanner.check(document.querySelector('.container'));
});

if (typeof module !== 'undefined') module.exports = SetupBanner;
