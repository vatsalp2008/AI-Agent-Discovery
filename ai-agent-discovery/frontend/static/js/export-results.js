/**
 * Turn a result set into a downloadable file.
 *
 * Serialisation is kept separate from the download so the formatting can be
 * tested without touching Blob or object URLs.
 */
const ExportResults = (() => {
    const COLUMNS = ['name', 'category', 'score', 'stars', 'url', 'description'];

    function row(result) {
        const meta = result.metadata || {};
        return {
            name: meta.name || result.name || '',
            category: meta.category || '',
            score: typeof result.score === 'number' ? result.score.toFixed(4) : '',
            stars: meta.stars == null ? '' : String(meta.stars),
            url: meta.url || '',
            description: meta.description || result.description || '',
        };
    }

    /** Quote a CSV field per RFC 4180: double the quotes, wrap if needed. */
    function csvField(value) {
        const text = String(value == null ? '' : value);
        if (/[",\n\r]/.test(text)) {
            return `"${text.replace(/"/g, '""')}"`;
        }
        return text;
    }

    function toCsv(results) {
        const lines = [COLUMNS.join(',')];
        results.forEach(result => {
            const record = row(result);
            lines.push(COLUMNS.map(c => csvField(record[c])).join(','));
        });
        // Trailing newline: POSIX tools expect a final line terminator.
        return lines.join('\r\n') + '\r\n';
    }

    function toJson(results, query) {
        return JSON.stringify({
            query: query || null,
            exported_at: new Date().toISOString(),
            count: results.length,
            results: results.map(row),
        }, null, 2);
    }

    /** A filesystem-safe name derived from the query. */
    function filename(query, extension) {
        const slug = (query || 'agents')
            .toLowerCase()
            .replace(/[^a-z0-9]+/g, '-')
            .replace(/^-+|-+$/g, '')
            .slice(0, 40) || 'agents';
        return `${slug}.${extension}`;
    }

    function download(text, name, mime) {
        const blob = new Blob([text], { type: mime });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = name;
        document.body.appendChild(link);
        link.click();
        link.remove();
        // Revoking immediately can cancel the download in some browsers.
        setTimeout(() => URL.revokeObjectURL(url), 1000);
    }

    function asCsv(results, query) {
        download(toCsv(results), filename(query, 'csv'), 'text/csv;charset=utf-8');
    }

    function asJson(results, query) {
        download(toJson(results, query), filename(query, 'json'), 'application/json');
    }

    return { COLUMNS, row, csvField, toCsv, toJson, filename, asCsv, asJson };
})();

if (typeof module !== 'undefined') module.exports = ExportResults;
