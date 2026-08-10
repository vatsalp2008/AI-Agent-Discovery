import { afterEach, describe, expect, it } from 'vitest';

import { ADMIN_HTML, bootPage, flush, stubFetch } from './helpers.js';

/** A raw catalogue record, as /api/admin/agents returns it. */
function record(name, category = 'Automation') {
    return {
        name, category,
        description: `${name} does things.`,
        tech_stack: ['Python'],
        github_stars: 10,
        url: 'https://example.com',
        use_case: `${name} use case`,
    };
}

function routes(overrides = {}) {
    return {
        '/api/admin/status': { body: { enabled: true, total: 2, catalogue_stale: false } },
        '/api/admin/agents': { body: { agents: [record('Aider'), record('Cursor')], total: 2 } },

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

describe('the audit trail', () => {
    function withAudit(entries, overrides = {}) {
        return routes({ '/api/admin/audit': { body: { entries } }, ...overrides });
    }

    it('lists recent changes', async () => {
        await boot(withAudit([
            { at: '2026-08-09T10:00:00+00:00', action: 'create', name: 'Aider', after: {} },
            { at: '2026-08-09T09:00:00+00:00', action: 'delete', name: 'Old', before: { category: 'Automation' } },
        ]));
        await flush();

        const rows = [...document.querySelectorAll('.audit-row')];
        expect(rows).toHaveLength(2);
        expect(rows[0].textContent).toContain('create');
        expect(rows[0].textContent).toContain('Aider');
    });

    it('names the fields an update changed', async () => {
        await boot(withAudit([{
            at: '2026-08-09T10:00:00+00:00', action: 'update', name: 'Aider',
            before: { description: 'Old', github_stars: 1 },
            after: { description: 'New', github_stars: 1 },
        }]));
        await flush();
        expect(document.querySelector('.audit-detail').textContent).toBe('changed description');
    });

    it('handles an update that changed nothing', async () => {
        await boot(withAudit([{
            at: '2026-08-09T10:00:00+00:00', action: 'update', name: 'Aider',
            before: { description: 'Same' }, after: { description: 'Same' },
        }]));
        await flush();
        expect(document.querySelector('.audit-detail').textContent).toBe('no field changed');
    });

    it('says so when nothing has been changed yet', async () => {
        await boot(withAudit([]));
        await flush();
        expect(document.getElementById('auditList').textContent).toContain('No changes recorded');
    });

    it('tolerates an unparseable timestamp', async () => {
        await boot(withAudit([{ at: 'not a date', action: 'create', name: 'X' }]));
        await flush();
        expect(document.querySelector('.audit-when').textContent).toBe('not a date');
    });

    it('does not break the page when the audit endpoint fails', async () => {
        await boot(routes({ '/api/admin/audit': { ok: false, status: 500, body: {} } }));
        await flush();
        expect(document.querySelectorAll('.admin-row').length).toBeGreaterThan(0);
    });
});

describe('undo', () => {
    it('asks before undoing', async () => {
        const real = window.confirm;
        window.confirm = () => false;
        try {
            const calls = await boot(routes({ '/api/admin/undo': { body: { undid: 'create', name: 'X' } } }));
            const before = calls.length;
            document.getElementById('undoBtn').click();
            await flush();
            expect(calls.length).toBe(before);
        } finally { window.confirm = real; }
    });

    it('reports what was undone', async () => {
        const real = window.confirm;
        window.confirm = () => true;
        try {
            await boot(routes({ '/api/admin/undo': { body: { undid: 'delete', name: 'Aider' } } }));
            document.getElementById('undoBtn').click();
            await flush();
            expect(document.getElementById('adminStatus').textContent).toContain('Undid the delete of Aider');
        } finally { window.confirm = real; }
    });

    it('surfaces nothing-to-undo', async () => {
        const real = window.confirm;
        window.confirm = () => true;
        try {
            await boot(routes({
                '/api/admin/undo': { ok: false, status: 404, body: { error: 'There is nothing to undo.' } },
            }));
            document.getElementById('undoBtn').click();
            await flush();
            expect(document.getElementById('adminError').textContent).toContain('nothing to undo');
            expect(document.getElementById('undoBtn').disabled).toBe(false);
        } finally { window.confirm = real; }
    });
});

describe('editing preserves every field', () => {
    it('loads use_case into the form', async () => {
        await boot();
        document.querySelector('.admin-row button').click();
        expect(document.getElementById('fieldUseCase').value).toBe('Aider use case');
    });

    it('submits use_case back unchanged', async () => {
        const calls = await boot();
        document.querySelector('.admin-row button').click();
        document.getElementById('fieldDescription').value = 'Edited.';
        submit();
        await flush();

        const put = calls.find(c => c.options && c.options.method === 'PUT');
        const body = JSON.parse(put.options.body);
        expect(body.use_case).toBe('Aider use case');
        expect(body.description).toBe('Edited.');
    });

    it('reads the catalogue from disk, not the search index', async () => {
        const calls = await boot();
        expect(calls.some(c => c.url.includes('/api/admin/agents'))).toBe(true);
        expect(calls.some(c => c.url.startsWith('/api/agents'))).toBe(false);
    });
});
