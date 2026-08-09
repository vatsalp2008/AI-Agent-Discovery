import { afterEach, describe, expect, it } from 'vitest';

import { ADMIN_HTML, bootPage, flush, stubFetch } from './helpers.js';

function agentRow(name, category = 'Automation') {
    return { name, metadata: { name, category, description: `${name} does things.`, stack: 'Python', stars: 10, url: 'https://example.com' } };
}

function routes(overrides = {}) {
    return {
        '/api/admin/status': { body: { enabled: true, total: 2, catalogue_stale: false } },
        '/api/agents': { body: { agents: [agentRow('Aider'), agentRow('Cursor')], metadata: {} } },
        '/api/admin/agents': { body: { agent: {}, total: 3 } },
        '/api/admin/reindex': { body: { indexed: 3 } },
        ...overrides,
    };
}

async function boot(r = routes()) {
    const calls = stubFetch(r);
    bootPage({ html: ADMIN_HTML, script: 'admin.js' });
    await flush();
    return calls;
}

function fill(values = {}) {
    document.getElementById('fieldName').value = values.name ?? 'NewAgent';
    document.getElementById('fieldCategory').value = values.category ?? 'Automation';
    document.getElementById('fieldDescription').value = values.description ?? 'Does things.';
    document.getElementById('fieldStack').value = values.stack ?? 'Python, Git';
    document.getElementById('fieldStars').value = values.stars ?? '42';
    document.getElementById('fieldUrl').value = values.url ?? 'https://example.com';
}

function submit() {
    document.getElementById('agentForm').dispatchEvent(
        new window.Event('submit', { bubbles: true, cancelable: true }));
}

afterEach(() => { delete globalThis.fetch; });

describe('gating', () => {
    it('shows the panel when editing is enabled', async () => {
        await boot();
        expect(document.getElementById('adminPanel').hidden).toBe(false);
        expect(document.getElementById('adminDisabled').hidden).toBe(true);
    });

    it('explains when editing is disabled', async () => {
        await boot(routes({ '/api/admin/status': { body: { enabled: false, total: 0 } } }));
        expect(document.getElementById('adminPanel').hidden).toBe(true);
        expect(document.getElementById('adminDisabled').hidden).toBe(false);
    });

    it('falls back to the disabled notice if status fails', async () => {
        await boot(routes({ '/api/admin/status': new Error('offline') }));
        expect(document.getElementById('adminDisabled').hidden).toBe(false);
    });
});

describe('listing', () => {
    it('lists the agents', async () => {
        await boot();
        const names = [...document.querySelectorAll('.admin-row-name')].map(n => n.textContent);
        expect(names).toEqual(['Aider', 'Cursor']);
    });

    it('shows the count', async () => {
        await boot();
        expect(document.getElementById('adminCount').textContent).toContain('2 agents');
    });

    it('warns when the index is behind', async () => {
        await boot(routes({ '/api/admin/status': { body: { enabled: true, total: 2, catalogue_stale: true } } }));
        expect(document.getElementById('adminStale').hidden).toBe(false);
    });

    it('offers existing categories as suggestions', async () => {
        await boot();
        const options = [...document.querySelectorAll('#categoryOptions option')].map(o => o.value);
        expect(options).toEqual(['Automation']);
    });
});

describe('creating', () => {
    it('posts the form as an agent record', async () => {
        const calls = await boot();
        fill();
        submit();
        await flush();

        const post = calls.find(c => c.options && c.options.method === 'POST' && c.url.includes('/api/admin/agents'));
        const body = JSON.parse(post.options.body);
        expect(body.name).toBe('NewAgent');
        expect(body.tech_stack).toEqual(['Python', 'Git']);
        expect(body.github_stars).toBe(42);
    });

    it('surfaces a validation error from the server', async () => {
        await boot(routes({
            '/api/admin/agents': { ok: false, status: 400, body: { error: "'name' is required" } },
        }));
        fill();
        submit();
        await flush();
        expect(document.getElementById('adminError').textContent).toContain("'name' is required");
    });

    it('does not submit the form normally', async () => {
        await boot();
        fill();
        const event = new window.Event('submit', { bubbles: true, cancelable: true });
        document.getElementById('agentForm').dispatchEvent(event);
        expect(event.defaultPrevented).toBe(true);
    });
});

describe('editing', () => {
    it('loads an agent into the form', async () => {
        await boot();
        document.querySelector('.admin-row button').click();
        expect(document.getElementById('fieldName').value).toBe('Aider');
        expect(document.getElementById('editingName').value).toBe('Aider');
        expect(document.getElementById('formHeading').textContent).toContain('Editing Aider');
        expect(document.getElementById('cancelBtn').hidden).toBe(false);
    });

    it('sends a PUT when editing', async () => {
        const calls = await boot();
        document.querySelector('.admin-row button').click();
        submit();
        await flush();

        const put = calls.find(c => c.options && c.options.method === 'PUT');
        expect(put.url).toContain('/api/admin/agents/Aider');
    });

    it('cancel returns to add mode', async () => {
        await boot();
        document.querySelector('.admin-row button').click();
        document.getElementById('cancelBtn').click();
        expect(document.getElementById('editingName').value).toBe('');
        expect(document.getElementById('formHeading').textContent).toBe('Add an agent');
    });
});

describe('deleting', () => {
    it('asks before deleting', async () => {
        const real = window.confirm;
        window.confirm = () => false;
        try {
            const calls = await boot();
            const before = calls.length;
            [...document.querySelectorAll('.admin-row button')][1].click();
            await flush();
            expect(calls.length).toBe(before);
        } finally { window.confirm = real; }
    });

    it('deletes when confirmed', async () => {
        const real = window.confirm;
        window.confirm = () => true;
        try {
            const calls = await boot();
            [...document.querySelectorAll('.admin-row button')][1].click();
            await flush();
            const del = calls.find(c => c.options && c.options.method === 'DELETE');
            expect(del.url).toContain('/api/admin/agents/Aider');
        } finally { window.confirm = real; }
    });
});

describe('reindexing', () => {
    it('reports how many agents were indexed', async () => {
        await boot();
        document.getElementById('reindexBtn').click();
        await flush();
        expect(document.getElementById('adminStatus').textContent).toContain('Reindexed 3');
    });

    it('re-enables the button after a failure', async () => {
        await boot(routes({ '/api/admin/reindex': { ok: false, status: 400, body: { error: 'broken catalogue' } } }));
        const button = document.getElementById('reindexBtn');
        button.click();
        await flush();
        expect(button.disabled).toBe(false);
        expect(document.getElementById('adminError').textContent).toContain('broken catalogue');
    });
});
