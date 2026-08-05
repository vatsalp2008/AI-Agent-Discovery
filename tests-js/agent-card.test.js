import { beforeAll, describe, expect, it } from 'vitest';

import { loadAgentCard, makeAgent } from './helpers.js';

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
