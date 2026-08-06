import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const STATIC_JS = resolve(here, '..', 'ai-agent-discovery', 'frontend', 'static', 'js');

/**
 * The static scripts are plain files that assign a global, not ES modules.
 * Evaluate one in the jsdom window so tests exercise exactly the file the
 * browser loads, with no build step or source duplication.
 */
export function loadScript(filename, globalName) {
    const source = readFileSync(resolve(STATIC_JS, filename), 'utf8');
    // eslint-disable-next-line no-eval
    (0, eval)(`${source}\n;globalThis.${globalName} = ${globalName};`);
    return globalThis[globalName];
}

export function loadAgentCard() {
    return loadScript('agent-card.js', 'AgentCard');
}

/** Minimal agent record shaped like a /api/search result. */
export function makeAgent(overrides = {}) {
    return {
        name: 'Cursor',
        description: 'An AI-powered code editor.',
        score: 0.91,
        metadata: {
            name: 'Cursor',
            category: 'Code Generation',
            stack: 'Electron,GPT-4,VS Code',
            stars: 35000,
            description: 'An AI-powered code editor.',
            url: 'https://cursor.sh',
        },
        ...overrides,
    };
}
