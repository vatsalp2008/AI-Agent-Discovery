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

        // Checked before the status: /api/health reports a stale catalogue as
        // status "ok" with a warning, since searches still work — they just
        // return the previous contents. Returning early on "ok" would hide
        // the most common thing worth telling someone about.
        if (health.catalogue_stale) {
            return {
                title: 'The index is out of date.',
                detail: 'data/agents.json has changed since it was built.',
                command: 'make seed',
            };
        }

        if (health.status === 'ok') return null;
        if (health.detail && health.detail.includes('embedding model')) {
            return {
                title: 'The index was built with a different embedding model.',
                detail: health.detail,
                command: 'make seed',
            };
        }
        return {
            title: 'No agents are indexed yet.',
            detail: 'The search index has not been built, so every search will come back empty.',
            command: 'make seed',
        };
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
