document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('submitForm');
    const closed = document.getElementById('submitClosed');
    const result = document.getElementById('submitResult');
    const button = document.getElementById('submitBtn');

    const fields = {
        name: document.getElementById('submitName'),
        category: document.getElementById('submitCategory'),
        description: document.getElementById('submitDescription'),
        stack: document.getElementById('submitStack'),
        url: document.getElementById('submitUrl'),
        use_case: document.getElementById('submitUseCase'),
    };

    function say(message, isError) {
        UI.showMessage(result, message, { error: Boolean(isError) });
    }

    function values() {
        return {
            name: fields.name.value.trim(),
            category: fields.category.value.trim(),
            description: fields.description.value.trim(),
            tech_stack: fields.stack.value.split(',').map(t => t.trim()).filter(Boolean),
            github_stars: 0,   // filled in later by the star refresh
            url: fields.url.value.trim(),
            use_case: fields.use_case.value.trim(),
        };
    }

    /** Offer the categories already in use, so proposals cluster sensibly. */
    async function fillCategories() {
        try {
            const response = await fetch('/api/categories');
            if (!response.ok) return;

            const categories = await response.json();
            if (!Array.isArray(categories)) return;

            document.getElementById('submitCategories').replaceChildren(
                ...categories.map(c => Object.assign(document.createElement('option'),
                                                     { value: c.name })));
        } catch (error) {
            console.error('Could not load categories:', error);
        }
    }

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        button.disabled = true;
        button.textContent = 'Submitting…';

        try {
            const response = await fetch('/api/submissions', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(values()),
            });
            const data = await response.json().catch(() => ({}));

            if (response.status === 403) {
                closed.hidden = false;
                form.hidden = true;
                return;
            }
            if (!response.ok) {
                say(data.error || `Submission failed (${response.status})`, true);
                return;
            }

            // The body is parsed with a fallback, so it may be {}. Naming
            // the agent is a nicety; reading through a missing `agent` would
            // throw into the catch below and report a failure for a
            // submission that succeeded.
            const name = data.agent && data.agent.name;
            say(name ? `Thanks — ${name} is queued for review.`
                     : 'Thanks — your submission is queued for review.');
            form.reset();
        } catch (error) {
            console.error(error);
            say('Could not reach the server.', true);
        } finally {
            button.disabled = false;
            button.textContent = 'Submit for review';
        }
    });

    fillCategories();
});
