import { afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest';

import { loadAgentCard, loadScript, makeAgent } from './helpers.js';

let AgentCard;

beforeAll(() => {
    AgentCard = loadAgentCard();
});

describe('escaping', () => {
    // Agent records come from hand-edited JSON, so every field is untrusted.
    it('does not execute markup in the agent name', () => {
        const card = AgentCard.create(makeAgent({
            metadata: { name: '<img src=x onerror="globalThis.pwned=1">', category: 'X' },
        }));
        expect(card.querySelector('img')).toBeNull();
        expect(globalThis.pwned).toBeUndefined();
        expect(card.querySelector('.agent-name').textContent).toContain('<img');
    });

    it('does not execute markup in the description', () => {
        const card = AgentCard.create(makeAgent({
            metadata: { name: 'a', description: '<script>globalThis.pwned=1</script>' },
        }));
        expect(card.querySelector('script')).toBeNull();
        expect(globalThis.pwned).toBeUndefined();
    });

    it('does not execute markup in tech stack entries', () => {
        const card = AgentCard.create(makeAgent({
            metadata: { name: 'a', stack: '<b>bold</b>,ok' },
        }));
        expect(card.querySelector('b')).toBeNull();
        expect(card.querySelectorAll('.tech-item')).toHaveLength(2);
        expect(card.querySelectorAll('.tech-item')[0].textContent).toBe('<b>bold</b>');
    });
});

describe('link safety', () => {
    it('renders http(s) links', () => {
        const link = AgentCard.create(makeAgent()).querySelector('.view-btn');
        expect(link.getAttribute('href')).toBe('https://cursor.sh/');
        expect(link.getAttribute('rel')).toBe('noopener noreferrer');
    });

    it.each([
        'javascript:globalThis.pwned=1',
        'data:text/html,<script>globalThis.pwned=1</script>',
        'vbscript:msgbox(1)',
    ])('refuses to link %s', (url) => {
        const link = AgentCard.create(makeAgent({ metadata: { name: 'a', url } })).querySelector('.view-btn');
        expect(link.hasAttribute('href')).toBe(false);
        expect(link.classList.contains('disabled')).toBe(true);
        expect(link.getAttribute('aria-disabled')).toBe('true');
    });

    it('disables the link when the url is missing', () => {
        const link = AgentCard.create(makeAgent({ metadata: { name: 'a' } })).querySelector('.view-btn');
        expect(link.hasAttribute('href')).toBe(false);
    });
});

describe('safeUrl', () => {
    it('accepts http and https', () => {
        expect(AgentCard.safeUrl('https://example.com')).toBe('https://example.com/');
        expect(AgentCard.safeUrl('http://example.com')).toBe('http://example.com/');
    });

    it.each([null, undefined, '', 'not a url', 'javascript:alert(1)'])('rejects %s', (value) => {
        expect(AgentCard.safeUrl(value)).toBeNull();
    });

    it('rejects relative urls rather than resolving them same-origin', () => {
        expect(AgentCard.safeUrl('/admin')).toBeNull();
        expect(AgentCard.safeUrl('../etc/passwd')).toBeNull();
    });
});

describe('formatStars', () => {
    it.each([
        [0, 'N/A'],
        [null, 'N/A'],
        [undefined, 'N/A'],
        ['not a number', 'N/A'],
        [999, '999'],
        [1000, '1.0k'],
        [35000, '35.0k'],
    ])('formats %s as %s', (input, expected) => {
        expect(AgentCard.formatStars(input)).toBe(expected);
    });
});

describe('parseStack', () => {
    it('accepts an array', () => {
        expect(AgentCard.parseStack(['A', 'B'])).toEqual(['A', 'B']);
    });

    it('splits a comma-separated string', () => {
        expect(AgentCard.parseStack('A,B')).toEqual(['A', 'B']);
    });

    it.each([null, undefined, 42, {}])('returns [] for %s', (value) => {
        expect(AgentCard.parseStack(value)).toEqual([]);
    });

    it('drops blank entries when rendering', () => {
        const card = AgentCard.create(makeAgent({ metadata: { name: 'a', stack: 'A, ,,B' } }));
        expect([...card.querySelectorAll('.tech-item')].map(n => n.textContent)).toEqual(['A', 'B']);
    });
});

describe('card content', () => {
    it('shows the relevance score as a percentage', () => {
        const card = AgentCard.create(makeAgent({ score: 0.91 }));
        expect(card.querySelector('.match-score').textContent).toBe('91% match');
    });

    it('omits the score badge when there is none', () => {
        const agent = makeAgent();
        delete agent.score;
        expect(AgentCard.create(agent).querySelector('.match-score')).toBeNull();
    });

    it('falls back to the top-level description', () => {
        const card = AgentCard.create(makeAgent({
            description: 'top level',
            metadata: { name: 'a' },
        }));
        expect(card.querySelector('.agent-description').textContent).toBe('top level');
    });

    it('falls back to placeholder text when nothing is available', () => {
        const card = AgentCard.create({ metadata: {} });
        expect(card.querySelector('.agent-description').textContent).toBe('No description available.');
        expect(card.querySelector('.agent-name').textContent).toBe('Unnamed agent');
        expect(card.querySelector('.agent-category').textContent).toBe('Uncategorized');
    });
});

describe('renderGrid', () => {
    it('replaces existing content', () => {
        const container = document.createElement('div');
        container.innerHTML = '<p>stale</p>';
        AgentCard.renderGrid(container, [makeAgent(), makeAgent()]);
        expect(container.querySelector('p')).toBeNull();
        expect(container.querySelectorAll('.agent-card')).toHaveLength(2);
    });

    it('handles an empty list', () => {
        const container = document.createElement('div');
        AgentCard.renderGrid(container, []);
        expect(container.querySelectorAll('.agent-card')).toHaveLength(0);
        expect(container.querySelector('.results-grid')).not.toBeNull();
    });
});

describe('compare links', () => {
    it('links an agent against its neighbours', () => {
        const agents = [makeAgent(), makeAgent({ metadata: { name: 'Aider' } }), makeAgent({ metadata: { name: 'Cline' } })];
        const link = AgentCard.compareLink(agents[0], agents);
        expect(link.getAttribute('href')).toBe('/compare?names=Cursor%2CAider%2CCline');
    });

    it('excludes the agent itself', () => {
        const agents = [makeAgent(), makeAgent({ metadata: { name: 'Aider' } })];
        expect(decodeURIComponent(AgentCard.compareLink(agents[0], agents).getAttribute('href')))
            .toBe('/compare?names=Cursor,Aider');
    });

    it('caps the comparison at three agents', () => {
        const agents = ['A', 'B', 'C', 'D', 'E'].map(n => makeAgent({ metadata: { name: n } }));
        const href = decodeURIComponent(AgentCard.compareLink(agents[0], agents).getAttribute('href'));
        expect(href.split(',')).toHaveLength(3);
    });

    it('returns nothing when there is no one to compare against', () => {
        const only = makeAgent();
        expect(AgentCard.compareLink(only, [only])).toBeNull();
    });

    it('appears in a rendered grid', () => {
        const container = document.createElement('div');
        AgentCard.renderGrid(container, [makeAgent(), makeAgent({ metadata: { name: 'Aider' } })]);
        expect(container.querySelectorAll('.compare-link').length).toBe(2);
    });

    it('is absent from a single-card grid', () => {
        const container = document.createElement('div');
        AgentCard.renderGrid(container, [makeAgent()]);
        expect(container.querySelector('.compare-link')).toBeNull();
    });
});

describe('save to collection', () => {
    beforeEach(() => {
        localStorage.clear();
        globalThis.Collections = loadScript('collections.js', 'Collections');
    });

    afterEach(() => {
        localStorage.clear();
        delete globalThis.Collections;
    });

    it('offers a save control when Collections is available', () => {
        const control = AgentCard.saveControl(makeAgent());
        expect(control.querySelector('.save-select')).not.toBeNull();
    });

    it('is absent when Collections is not loaded', () => {
        delete globalThis.Collections;
        expect(AgentCard.saveControl(makeAgent())).toBeNull();
    });

    it('lists existing collections', () => {
        Collections.create('Coding');
        Collections.create('Research');
        const options = [...AgentCard.saveControl(makeAgent()).querySelectorAll('option')]
            .map(o => o.textContent);
        expect(options).toEqual(['Save to…', 'Coding', 'Research', '+ New collection…']);
    });

    it('adds the agent to the chosen collection', () => {
        Collections.create('Coding');
        const control = AgentCard.saveControl(makeAgent());
        const select = control.querySelector('.save-select');
        select.value = 'Coding';
        select.dispatchEvent(new window.Event('change'));
        expect(Collections.agentsIn('Coding')).toEqual(['Cursor']);
    });

    it('marks and disables a collection already holding the agent', () => {
        Collections.create('Coding');
        Collections.add('Coding', 'Cursor');
        const option = [...AgentCard.saveControl(makeAgent()).querySelectorAll('option')]
            .find(o => o.value === 'Coding');
        expect(option.textContent).toContain('✓');
        expect(option.disabled).toBe(true);
    });

    it('creates a collection on the fly', () => {
        const realPrompt = window.prompt;
        window.prompt = () => 'Fresh';
        try {
            const select = AgentCard.saveControl(makeAgent()).querySelector('.save-select');
            select.value = '__new__';
            select.dispatchEvent(new window.Event('change'));
            expect(Collections.agentsIn('Fresh')).toEqual(['Cursor']);
        } finally {
            window.prompt = realPrompt;
        }
    });

    it('does nothing when the new-collection prompt is cancelled', () => {
        const realPrompt = window.prompt;
        window.prompt = () => null;
        try {
            const select = AgentCard.saveControl(makeAgent()).querySelector('.save-select');
            select.value = '__new__';
            select.dispatchEvent(new window.Event('change'));
            expect(Collections.names()).toEqual([]);
        } finally {
            window.prompt = realPrompt;
        }
    });

    it('appears on rendered cards', () => {
        Collections.create('Coding');
        const container = document.createElement('div');
        AgentCard.renderGrid(container, [makeAgent(), makeAgent({ metadata: { name: 'Aider' } })]);
        expect(container.querySelectorAll('.save-select')).toHaveLength(2);
    });
});

describe('match labelling', () => {
    it('shows a percentage for a semantic match', () => {
        const card = AgentCard.create(makeAgent({ score: 0.82, match: 'semantic' }));
        expect(card.querySelector('.match-score').textContent).toBe('82% match');
        expect(card.querySelector('.match-name')).toBeNull();
    });

    it('does not dress a name match up as 100% similarity', () => {
        const card = AgentCard.create(makeAgent({ score: 1.0, match: 'name' }));
        const label = card.querySelector('.match-score');
        expect(label.textContent).toBe('name match');
        expect(label.classList.contains('match-name')).toBe(true);
        expect(label.title).toContain('name');
    });

    it('treats an unlabelled result as semantic', () => {
        const agent = makeAgent({ score: 0.5 });
        delete agent.match;
        expect(AgentCard.create(agent).querySelector('.match-score').textContent).toBe('50% match');
    });

    it('shows nothing when there is no score', () => {
        const agent = makeAgent();
        delete agent.score;
        expect(AgentCard.create(agent).querySelector('.match-score')).toBeNull();
    });
});

describe('project health', () => {
    /** status lives in metadata, beside category and stars. */
    function withStatus(status) {
        const agent = makeAgent();
        return AgentCard.create({ ...agent, metadata: { ...agent.metadata, status } });
    }

    it('says when a project is archived', () => {
        const badge = withStatus('archived').querySelector('.agent-status');

        expect(badge.textContent).toBe('Archived');
        expect(badge.title).toContain('archived on GitHub');
    });

    it('says when a project has gone quiet', () => {
        expect(withStatus('dormant').querySelector('.agent-status').textContent)
            .toBe('Not updated recently');
    });

    it('says nothing for a healthy project', () => {
        /** A badge on every card stops meaning anything, and 204 of 223
         *  entries are active. */
        expect(AgentCard.create(makeAgent()).querySelector('.agent-status')).toBeNull();
        expect(withStatus('active').querySelector('.agent-status')).toBeNull();
    });

    it('ignores a status it does not recognise', () => {
        expect(withStatus('retired').querySelector('.agent-status')).toBeNull();
    });

    it('carries the meaning in words, not only colour', () => {
        /** The wording is the part a screen reader reads. */
        for (const status of ['archived', 'dormant']) {
            expect(withStatus(status).querySelector('.agent-status')
                .textContent.trim().length).toBeGreaterThan(5);
        }
    });
});

describe('where to go instead', () => {
    function withMeta(extra) {
        const agent = makeAgent();
        return AgentCard.create({ ...agent, metadata: { ...agent.metadata, ...extra } });
    }

    it('links each alternative on an archived card', () => {
        const card = withMeta({ status: 'archived', alternatives: 'Langflow,Dify' });
        const links = [...card.querySelectorAll('.agent-alternatives a')];

        expect(links.map(a => a.textContent)).toEqual(['Langflow', 'Dify']);
        expect(links[0].getAttribute('href')).toBe('/agent/Langflow');
    });

    it('encodes a name that needs it', () => {
        const card = withMeta({ status: 'archived', alternatives: 'Weights & Biases' });

        expect(card.querySelector('.agent-alternatives a').getAttribute('href'))
            .toBe('/agent/Weights%20%26%20Biases');
    });

    it('says nothing for a dormant project', () => {
        /** Quiet is not finished. Telling someone to leave a tool that still
         *  works is not the same as telling them a dead one is dead. */
        expect(withMeta({ status: 'dormant', alternatives: 'Langflow' })
            .querySelector('.agent-alternatives')).toBeNull();
    });

    it('says nothing for a healthy project', () => {
        expect(withMeta({ alternatives: 'Langflow' })
            .querySelector('.agent-alternatives')).toBeNull();
    });

    it('says nothing when an archived entry names none', () => {
        expect(withMeta({ status: 'archived' })
            .querySelector('.agent-alternatives')).toBeNull();
        expect(withMeta({ status: 'archived', alternatives: '' })
            .querySelector('.agent-alternatives')).toBeNull();
    });

    it('ignores stray separators', () => {
        /** The field is comma-joined into FAISS metadata, which stores only
         *  scalars, so the split has to tolerate what a hand edit leaves. */
        const card = withMeta({ status: 'archived', alternatives: 'Langflow, ,Dify,' });

        expect([...card.querySelectorAll('.agent-alternatives a')].map(a => a.textContent))
            .toEqual(['Langflow', 'Dify']);
    });
});
