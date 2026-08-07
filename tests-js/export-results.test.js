import { beforeAll, describe, expect, it } from 'vitest';

import { loadScript, makeAgent } from './helpers.js';

let Exp;

beforeAll(() => { Exp = loadScript('export-results.js', 'ExportResults'); });

describe('CSV', () => {
    it('writes a header and one row per result', () => {
        const csv = Exp.toCsv([makeAgent(), makeAgent({ metadata: { name: 'Aider' } })]);
        const lines = csv.trim().split('\r\n');
        expect(lines[0]).toBe('name,category,score,stars,url,description');
        expect(lines).toHaveLength(3);
    });

    it('quotes fields containing a comma', () => {
        expect(Exp.csvField('a,b')).toBe('"a,b"');
    });

    it('escapes embedded quotes by doubling them', () => {
        expect(Exp.csvField('say "hi"')).toBe('"say ""hi"""');
    });

    it('quotes fields containing a newline', () => {
        expect(Exp.csvField('line1\nline2')).toBe('"line1\nline2"');
    });

    it('leaves plain fields unquoted', () => {
        expect(Exp.csvField('plain')).toBe('plain');
    });

    it('does not let a description break the row structure', () => {
        const csv = Exp.toCsv([makeAgent({
            metadata: { name: 'X', category: 'C', description: 'has, comma and "quotes"' },
        })]);
        expect(csv.trim().split('\r\n')).toHaveLength(2);
    });

    it('ends with a newline', () => {
        expect(Exp.toCsv([makeAgent()]).endsWith('\r\n')).toBe(true);
    });

    it('handles an empty result set', () => {
        expect(Exp.toCsv([]).trim()).toBe('name,category,score,stars,url,description');
    });
});

describe('JSON', () => {
    it('includes the query, count and results', () => {
        const payload = JSON.parse(Exp.toJson([makeAgent()], 'code editor'));
        expect(payload.query).toBe('code editor');
        expect(payload.count).toBe(1);
        expect(payload.results[0].name).toBe('Cursor');
    });

    it('records when the export happened', () => {
        const payload = JSON.parse(Exp.toJson([], null));
        expect(Number.isNaN(Date.parse(payload.exported_at))).toBe(false);
    });

    it('formats the score to four places', () => {
        const payload = JSON.parse(Exp.toJson([makeAgent({ score: 0.912345 })]));
        expect(payload.results[0].score).toBe('0.9123');
    });

    it('tolerates a result with no metadata', () => {
        const payload = JSON.parse(Exp.toJson([{ name: 'Bare' }]));
        expect(payload.results[0].name).toBe('Bare');
        expect(payload.results[0].category).toBe('');
    });
});

describe('filenames', () => {
    it('slugifies the query', () => {
        expect(Exp.filename('I need a Code Editor!', 'csv')).toBe('i-need-a-code-editor.csv');
    });

    it('falls back when there is no query', () => {
        expect(Exp.filename('', 'json')).toBe('agents.json');
    });

    it('falls back when the query has no usable characters', () => {
        expect(Exp.filename('!!!', 'csv')).toBe('agents.csv');
    });

    it('caps the length', () => {
        expect(Exp.filename('x'.repeat(200), 'csv').length).toBeLessThanOrEqual(45);
    });
});
