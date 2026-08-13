document.addEventListener('DOMContentLoaded', () => {
    const panel = document.getElementById('adminPanel');
    const disabled = document.getElementById('adminDisabled');
    const form = document.getElementById('agentForm');
    const list = document.getElementById('adminList');
    const auditList = document.getElementById('auditList');
    const rowFilter = document.getElementById('adminFilter');
    const submissionsSection = document.getElementById('submissionsSection');
    const submissionsList = document.getElementById('submissionsList');
    const submissionsCount = document.getElementById('submissionsCount');
    const rowCount = document.getElementById('adminFilterCount');
    const result = document.getElementById('adminResult');
    const countEl = document.getElementById('adminCount');
    const staleEl = document.getElementById('adminStale');
    const heading = document.getElementById('formHeading');
    const saveBtn = document.getElementById('saveBtn');
    const cancelBtn = document.getElementById('cancelBtn');
    const editingName = document.getElementById('editingName');

    // Filter for the row list. The catalogue is served whole (it is a local
    // file), so filtering happens here rather than as another request.
    let allRecords = [];

    const fields = {
        name: document.getElementById('fieldName'),
        category: document.getElementById('fieldCategory'),
        description: document.getElementById('fieldDescription'),
        stack: document.getElementById('fieldStack'),
        stars: document.getElementById('fieldStars'),
        url: document.getElementById('fieldUrl'),
        use_case: document.getElementById('fieldUseCase'),
    };

    const say = UI.reporter(result);

    function formValues() {
        return {
            name: fields.name.value.trim(),
            category: fields.category.value.trim(),
            description: fields.description.value.trim(),
            tech_stack: fields.stack.value.split(',').map(t => t.trim()).filter(Boolean),
            github_stars: Number(fields.stars.value) || 0,
            url: fields.url.value.trim(),
            use_case: fields.use_case.value.trim(),
        };
    }

    function resetForm() {
        form.reset();
        editingName.value = '';
        heading.textContent = 'Add an agent';
        saveBtn.textContent = 'Add agent';
        cancelBtn.hidden = true;
    }

    function startEdit(agent) {
        editingName.value = agent.name;
        fields.name.value = agent.name;
        fields.category.value = agent.category || '';
        fields.description.value = agent.description || '';
        fields.stack.value = (agent.tech_stack || []).join(', ');
        fields.stars.value = agent.github_stars || 0;
        fields.url.value = agent.url || '';
        fields.use_case.value = agent.use_case || '';

        heading.textContent = `Editing ${agent.name}`;
        saveBtn.textContent = 'Save changes';
        cancelBtn.hidden = false;
        fields.name.focus();
    }

    function row(agent) {
        const item = document.createElement('div');
        item.className = 'admin-row';

        const label = document.createElement('span');
        label.className = 'admin-row-name';
        label.textContent = agent.name;
        item.appendChild(label);

        const category = document.createElement('span');
        category.className = 'admin-row-category';
        category.textContent = agent.category || '';
        item.appendChild(category);

        const edit = document.createElement('button');
        edit.type = 'button';
        edit.className = 'control-button';
        edit.textContent = 'Edit';
        edit.setAttribute('aria-label', `Edit ${agent.name}`);
        edit.addEventListener('click', () => startEdit(agent));
        item.appendChild(edit);

        const remove = document.createElement('button');
        remove.type = 'button';
        remove.className = 'control-button';
        remove.textContent = 'Delete';
        remove.setAttribute('aria-label', `Delete ${agent.name}`);
        remove.addEventListener('click', async () => {
            if (!window.confirm(`Delete ${agent.name}?`)) return;
            await send(`/api/admin/agents/${encodeURIComponent(agent.name)}`, 'DELETE',
                       undefined, { keepForm: true });
        });
        item.appendChild(remove);

        return item;
    }

    function auditRow(entry) {
        const row = document.createElement('div');
        row.className = 'audit-row';

        const when = document.createElement('span');
        when.className = 'audit-when';
        // The log stores UTC; show it in the reader's own timezone.
        const parsed = new Date(entry.at);
        when.textContent = Number.isNaN(parsed.getTime()) ? (entry.at || '') : parsed.toLocaleString();
        row.appendChild(when);

        const action = document.createElement('span');
        action.className = `audit-action audit-${entry.action}`;
        action.textContent = entry.action;
        row.appendChild(action);

        const name = document.createElement('span');
        name.className = 'audit-name';
        name.textContent = entry.name || '';
        row.appendChild(name);

        // What actually changed, so the line is useful without expanding it.
        const detail = document.createElement('span');
        detail.className = 'audit-detail';
        if (entry.action === 'update' && entry.before && entry.after) {
            const changed = Object.keys(entry.after).filter(
                k => JSON.stringify(entry.after[k]) !== JSON.stringify(entry.before[k]));
            detail.textContent = changed.length ? `changed ${changed.join(', ')}` : 'no field changed';
        } else if (entry.action === 'delete' && entry.before) {
            detail.textContent = entry.before.category || '';
        }
        row.appendChild(detail);

        return row;
    }

    async function refreshAudit() {
        if (!auditList) return;
        try {
            const response = await fetch('/api/admin/audit?limit=20');
            if (!response.ok) return;

            const entries = (await response.json()).entries || [];
            if (entries.length === 0) {
                const empty = document.createElement('p');
                empty.className = 'result-message';
                empty.textContent = 'No changes recorded yet.';
                auditList.replaceChildren(empty);
                return;
            }
            auditList.replaceChildren(...entries.map(auditRow));
        } catch (error) {
            console.error('Could not load the audit log:', error);
        }
    }

    /**
     * Load the catalogue from disk via the admin endpoint.
     *
     * Not /api/agents: that comes from the search index, which omits
     * `use_case` and lags unindexed edits. Editing from it would blank the
     * field on save and revert earlier unindexed changes.
     */
    async function refresh() {
        try {
            const status = await (await fetch('/api/admin/status')).json();
            countEl.textContent = `${status.total} agents in the catalogue`;
            staleEl.hidden = !status.catalogue_stale;

            const response = await fetch('/api/admin/agents');
            if (!response.ok) throw new Error(`Request failed with status ${response.status}`);

            const body = await response.json();
            const agents = (body.agents || []).slice().sort(
                (a, b) => String(a.name || '').localeCompare(String(b.name || '')));

            allRecords = agents;

            const seen = [...new Set(agents.map(a => a.category).filter(Boolean))].sort();
            document.getElementById('categoryOptions').replaceChildren(
                ...seen.map(c => Object.assign(document.createElement('option'), { value: c })));

            renderRows();
            await refreshSubmissions();
            await refreshAudit();
        } catch (error) {
            console.error(error);
            say('Could not load the catalogue.', true);
        }
    }

    /**
     * `keepForm` is passed by the caller rather than inferred from the
     * response: a delete must not discard an edit in progress on another row,
     * and deciding that from the response shape would break if the API's
     * body ever changed.
     */
    /** One card per pending proposal, with approve and reject. */
    function submissionRow(entry) {
        const agent = entry.agent || {};
        const row = document.createElement('div');
        row.className = 'submission-row';

        const name = document.createElement('span');
        name.className = 'admin-row-name';
        name.textContent = agent.name || '(unnamed)';
        row.appendChild(name);

        const detail = document.createElement('span');
        detail.className = 'admin-row-category';
        detail.textContent = `${agent.category || ''} — ${agent.description || ''}`;
        row.appendChild(detail);

        const approve = document.createElement('button');
        approve.type = 'button';
        approve.className = 'control-button';
        approve.textContent = 'Approve';
        approve.setAttribute('aria-label', `Approve ${agent.name}`);
        approve.addEventListener('click', () =>
            send(`/api/admin/submissions/${encodeURIComponent(entry.id)}/approve`, 'POST',
                 undefined, { keepForm: true }));
        row.appendChild(approve);

        const reject = document.createElement('button');
        reject.type = 'button';
        reject.className = 'control-button';
        reject.textContent = 'Reject';
        reject.setAttribute('aria-label', `Reject ${agent.name}`);
        reject.addEventListener('click', () => {
            const note = window.prompt(`Why is ${agent.name} being rejected? (optional)`);
            if (note === null) return;   // cancelled
            send(`/api/admin/submissions/${encodeURIComponent(entry.id)}/reject`, 'POST',
                 { note }, { keepForm: true });
        });
        row.appendChild(reject);

        return row;
    }

    async function refreshSubmissions() {
        if (!submissionsSection) return;
        try {
            const response = await fetch('/api/admin/submissions?status=pending');
            if (!response.ok) return;

            const body = await response.json();
            const entries = body.submissions || [];

            submissionsSection.hidden = entries.length === 0;
            if (submissionsCount) submissionsCount.textContent = `(${entries.length})`;
            submissionsList.replaceChildren(...entries.map(submissionRow));
        } catch (error) {
            console.error('Could not load submissions:', error);
        }
    }

    /** Draw the rows matching the current filter. */
    function renderRows() {
        const needle = (rowFilter && rowFilter.value.trim().toLowerCase()) || '';
        const matching = needle
            ? allRecords.filter(a =>
                String(a.name || '').toLowerCase().includes(needle)
                || String(a.category || '').toLowerCase().includes(needle))
            : allRecords;

        if (matching.length === 0) {
            const empty = document.createElement('p');
            empty.className = 'result-message';
            empty.textContent = needle ? 'No agents match that filter.' : 'The catalogue is empty.';
            list.replaceChildren(empty);
        } else {
            list.replaceChildren(...matching.map(row));
        }

        if (rowCount) {
            rowCount.textContent = needle
                ? `${matching.length} of ${allRecords.length} shown`
                : '';
        }
    }

    async function send(url, method, body, { keepForm = false } = {}) {
        try {
            const response = await fetch(url, {
                method,
                headers: body ? { 'Content-Type': 'application/json' } : {},
                body: body ? JSON.stringify(body) : undefined,
            });
            const data = await response.json().catch(() => ({}));

            if (!response.ok) {
                say(data.error || `Request failed (${response.status})`, true);
                return false;
            }
            say(keepForm
                ? `Deleted ${data.deleted || 'agent'}.`
                : 'Saved. Rebuild the index to apply it.');
            if (!keepForm) resetForm();
            await refresh();
            return true;
        } catch (error) {
            console.error(error);
            say('Could not reach the server.', true);
            return false;
        }
    }

    /**
     * Warn about near-duplicates before adding. Advisory: the person decides,
     * since "similar" is not "the same". Skipped when editing an existing
     * agent, where a close match to itself is expected.
     */
    async function confirmNotDuplicate(values) {
        try {
            const response = await fetch('/api/admin/similar-check', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: values.name, description: values.description }),
            });
            if (!response.ok) return true;

            const data = await response.json();
            const similar = data.similar || [];
            if (similar.length === 0) return true;

            const names = similar.map(s => `${s.name} (${Math.round(s.score * 100)}% similar)`);
            return window.confirm(
                `The catalogue already has:\n\n${names.join('\n')}\n\nAdd anyway?`);
        } catch (error) {
            console.error('Could not check for duplicates:', error);
            return true;   // never block a save on this
        }
    }

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const existing = editingName.value;
        const values = formValues();
        if (existing) {
            await send(`/api/admin/agents/${encodeURIComponent(existing)}`, 'PUT', values);
        } else {
            if (!(await confirmNotDuplicate(values))) return;
            await send('/api/admin/agents', 'POST', values);
        }
    });

    cancelBtn.addEventListener('click', resetForm);

    if (rowFilter) {
        rowFilter.addEventListener('input', renderRows);
    }

    const undoBtn = document.getElementById('undoBtn');
    if (undoBtn) {
        undoBtn.addEventListener('click', async () => {
            if (!window.confirm('Undo the most recent catalogue change?')) return;
            undoBtn.disabled = true;
            try {
                const response = await fetch('/api/admin/undo', { method: 'POST' });
                const data = await response.json().catch(() => ({}));
                if (response.ok) {
                    say(`Undid the ${data.undid} of ${data.name}. Rebuild the index to apply it.`);
                    await refresh();
                } else {
                    say(data.error || 'Could not undo.', true);
                }
            } catch (error) {
                console.error(error);
                say('Could not reach the server.', true);
            } finally {
                undoBtn.disabled = false;
            }
        });
    }

    document.getElementById('reindexBtn').addEventListener('click', async (e) => {
        const button = e.currentTarget;
        button.disabled = true;
        button.textContent = 'Rebuilding…';
        try {
            const response = await fetch('/api/admin/reindex', { method: 'POST' });
            const data = await response.json().catch(() => ({}));
            say(response.ok ? `Reindexed ${data.indexed} agents.` : (data.error || 'Reindex failed.'),
                !response.ok);
            if (response.ok) await refresh();
        } catch (error) {
            console.error(error);
            say('Could not reach the server.', true);
        } finally {
            button.disabled = false;
            button.textContent = 'Rebuild index';
        }
    });

    (async () => {
        try {
            const status = await (await fetch('/api/admin/status')).json();
            if (!status.enabled) {
                disabled.hidden = false;
                return;
            }
            panel.hidden = false;
            await refresh();
        } catch (error) {
            console.error(error);
            disabled.hidden = false;
        }
    })();
});
