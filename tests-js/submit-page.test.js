import { afterEach, describe, expect, it } from 'vitest';

import { bootPage, flush, stubFetch, SUBMIT_HTML } from './helpers.js';

function routes(overrides = {}) {
    return {
        '/api/categories': { body: [{ name: 'Automation', count: 8 }, { name: 'Research', count: 6 }] },
        '/api/submissions': { ok: true, status: 202, body: { id: 'abc', status: 'pending', agent: { name: 'Proposed' } } },
        ...overrides,
    };
}

async function boot(r = routes()) {
    const calls = stubFetch(r);
    bootPage({ html: SUBMIT_HTML, script: 'submit.js' });
    await flush();
    return calls;
}

function fill(values = {}) {
    document.getElementById('submitName').value = values.name ?? 'Proposed';
    document.getElementById('submitCategory').value = values.category ?? 'Automation';
    document.getElementById('submitDescription').value = values.description ?? 'It does a useful thing worth describing at length.';
    document.getElementById('submitStack').value = values.stack ?? 'Python, Git';
    document.getElementById('submitUrl').value = values.url ?? 'https://example.com';
}

function submit() {
    document.getElementById('submitForm').dispatchEvent(
        new window.Event('submit', { bubbles: true, cancelable: true }));
}

afterEach(() => { delete globalThis.fetch; });

describe('the form', () => {
    it('offers the categories already in use', async () => {
        await boot();
        expect([...document.querySelectorAll('#submitCategories option')].map(o => o.value))
            .toEqual(['Automation', 'Research']);
    });

    it('posts the proposal', async () => {
        const calls = await boot();
        fill();
        submit();
        await flush();

        const call = calls.find(c => c.options && c.options.method === 'POST');
        const body = JSON.parse(call.options.body);
        expect(body.name).toBe('Proposed');
        expect(body.tech_stack).toEqual(['Python', 'Git']);
    });

    it('confirms and clears on success', async () => {
        await boot();
        fill();
        submit();
        await flush();

        expect(document.getElementById('submitStatus').textContent).toContain('queued for review');
        expect(document.getElementById('submitName').value).toBe('');
    });

    it('surfaces a validation error from the server', async () => {
        await boot(routes({
            '/api/submissions': { ok: false, status: 400, body: { error: "'name' is required" } },
        }));
        fill();
        submit();
        await flush();
        expect(document.getElementById('submitError').textContent).toContain("'name' is required");
    });

    it('reports being rate limited', async () => {
        await boot(routes({
            '/api/submissions': { ok: false, status: 429, body: { error: 'Too many submissions. Try again shortly.' } },
        }));
        fill();
        submit();
        await flush();
        expect(document.getElementById('submitError').textContent).toContain('Too many');
    });

    it('hides the form when submissions are closed', async () => {
        await boot(routes({
            '/api/submissions': { ok: false, status: 403, body: { error: 'Submissions are closed.' } },
        }));
        fill();
        submit();
        await flush();

        expect(document.getElementById('submitClosed').hidden).toBe(false);
        expect(document.getElementById('submitForm').hidden).toBe(true);
    });

    it('re-enables the button after a failure', async () => {
        await boot(routes({ '/api/submissions': new Error('offline') }));
        fill();
        submit();
        await flush();

        const button = document.getElementById('submitBtn');
        expect(button.disabled).toBe(false);
        expect(button.textContent).toBe('Submit for review');
    });

    it('does not submit the form normally', async () => {
        await boot();
        fill();
        const event = new window.Event('submit', { bubbles: true, cancelable: true });
        document.getElementById('submitForm').dispatchEvent(event);
        expect(event.defaultPrevented).toBe(true);
    });
});
