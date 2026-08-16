# API Reference

Every endpoint returns JSON, including errors. A machine-readable
description is served at `/api/openapi.json`, generated from the live URL
map so it cannot drift from the routes that exist.

See the [README](../README.md) for setup and the [contributing
guide](../CONTRIBUTING.md) for conventions.

## Contents

- [Search agents](#search-agents)
- [List agents (paginated, filterable, sortable)](#list-agents-paginated-filterable-sortable)
- [Get a single agent](#get-a-single-agent)
- [List categories](#list-categories)
- [Similar agents](#similar-agents)
- [Compare agents](#compare-agents)
- [List technologies](#list-technologies)
- [Statistics](#statistics)
- [Health](#health)
- [Proposing an agent](#proposing-an-agent)
- [Reviewing submissions](#reviewing-submissions)
- [Catalogue editing](#catalogue-editing)
- [Machine-readable spec](#machine-readable-spec)
- [Response headers](#response-headers)

## Search agents

```bash
POST /api/search
Content-Type: application/json

{
  "query": "I need an agent to write Python code",
  "limit": 5,                       // optional, 1..SEARCH_MAX_LIMIT
  "category": "Code Generation",    // optional, case-insensitive
  "min_score": 0.5,                 // optional, 0..1 — drops weaker matches
  "summarize": true                 // optional, adds an LLM overview
}
```

**Response:**
```json
{
  "results": [
    {
      "name": "Cursor",
      "description": "An AI-powered code editor...",
      "matched_text": "Name: Cursor\nDescription: ...",
      "metadata": {
        "name": "Cursor",
        "category": "Code Generation",
        "stack": "Electron,GPT-4,VS Code",
        "stars": 35000,
        "description": "An AI-powered code editor...",
        "url": "https://cursor.sh"
      },
      "distance": 0.42,
      "score": 0.7042,
      "match": "semantic"
    }
  ],
  "summary": "Cursor is a full editor, while Aider works from the terminal.",
  "metadata": {
    "count": 1, "limit": 5, "category": "Code Generation",
    "confident": true, "min_score": null,
    "summarized": true, "duration": "1.31s"
  }
}
```

`score` is the cosine similarity between the query and the agent, recovered
from the L2 distance as `1 - d²/2` (exact for the unit-length vectors these
embedding models emit). Measured against this catalogue: a verbatim
description scores ≈0.91, a good semantic match ≈0.71, and an unrelated query
≈0.34. `description` is the agent's own text; `matched_text` is the composite
string that was actually embedded.

**Exact names.** `match` is `"semantic"` for a normal similarity hit and
`"name"` when the query was exactly an agent's name. A name match is placed
first and scored `1.0`, and the UI labels it "name match" rather than "100%
match" — it is not a similarity score, and presenting it as one would overstate
it.

This exists because similarity alone is not enough for a product named after an
ordinary word: searching `Evidently` did not return the tool called Evidently
anywhere in the top ten, since the bare adverb reads as generic English. Only a
full-string, case-insensitive match on the name qualifies — a substring would
let `Code` hijack the ranking.

A name match always scores `1.0`, whether the vector search happened to return
the agent or it had to be looked up. That is deliberate: otherwise the same
query would score differently depending on an accident of retrieval, and a
`min_score` filter could drop the very agent you named.

**Weak matches.** Vector search always returns *something*, so a nonsense query
still comes back with a full page of results. `metadata.confident` is `false`
when the best result scored below `SEARCH_MIN_SCORE` (default `0.5`); the web UI
shows a plain "nothing matched well" notice in that case. Results are flagged,
not hidden — an obscure but genuine query should still return its best guess.
Pass `min_score` if you want them dropped outright instead.

The default sits in a measured gap: against this catalogue, genuine queries
score 0.63–0.85 and nonsense queries 0.27–0.42.

`summary` is `null` unless you pass `"summarize": true` **and** generation
succeeds. `metadata.summarized` tells you which happened. Generation is
best-effort: if the chat model is missing, slow, or Ollama is down, you still
get your results with `summary: null`. No overview is generated for
low-confidence results, since a confident summary of irrelevant tools is worse
than none.

## List agents (paginated, filterable, sortable)

```bash
GET /api/agents?limit=20&offset=0
GET /api/agents?category=Code%20Generation      # case-insensitive
GET /api/agents?tech=Python                     # matches whole stack entries
GET /api/agents?q=cursor                        # substring of name or description
GET /api/agents?min_stars=10000&max_stars=50000 # by popularity
GET /api/agents?sort=stars                      # name | stars | category
GET /api/agents?sort=name&order=desc            # asc | desc
```

```json
{
  "agents": [ { "name": "Aider", "description": "...", "metadata": { } } ],
  "metadata": {
    "total": 106, "count": 20, "limit": 20, "offset": 0,
    "category": null, "tech": null, "q": null,
    "min_stars": null, "max_stars": null, "sort": "name", "order": "asc",
    "has_more": true
  }
}
```

`sort=stars` defaults to descending, the others to ascending. Filters combine.
`q` is plain substring matching, deliberately not semantic: it answers "find
the agent I can already name", which vector search handles poorly for short
literal strings.

## Get a single agent

```bash
GET /api/agents/Cursor      # case-insensitive; 404 if unknown
```

## List categories

```bash
GET /api/categories
# [{"name": "Code Generation", "count": 6}, {"name": "Research", "count": 4}]
```

## Similar agents

```bash
GET /api/agents/Cursor/similar?limit=3
```

```json
{
  "agents": [ { "name": "Windsurf", "score": 0.83, "metadata": { } } ],
  "metadata": { "of": "Cursor", "count": 3, "limit": 3 }
}
```

Excludes the agent from its own results, and over-fetches so a request for
three neighbours returns three rather than two.

## Compare agents

```bash
GET /api/compare?names=Claude%20Code,Aider,Cline
```

```json
{
  "agents": [ { "name": "Claude Code", "metadata": { } } ],
  "metadata": { "requested": 3, "count": 3, "missing": [] }
}
```

Unknown names come back in `metadata.missing` instead of failing the request,
so one typo does not discard the agents that did resolve. Capped at
`COMPARE_MAX_AGENTS` (default 8); more than that is a `400`, and the compare
page stops its picker at the same number so the limit never arrives as a
failed request.

## Hiding abandoned projects

Both `POST /api/search` and `GET /api/agents` take a **maintained** filter that
leaves out entries whose `status` is `archived` or `dormant`:

```bash
POST /api/search   {"query": "prompt injection guardrails", "maintained": true}
GET  /api/agents?maintained=1
```

The search filter runs *during* the scan rather than trimming the results
afterwards, so a page of ten is still a page of ten — an archived project is
replaced by the next live one, not simply dropped. `/api/search` wants a real
boolean; the query string on `/api/agents` accepts `1`, `true`, `yes` or `on`,
since a query string has no booleans.

The MCP `search_agents` tool takes the same argument, which is worth setting
when the answer is a recommendation rather than a survey.

## Catalogue history

```bash
GET /api/changelog?limit=50
# {"entries": [{"commit": "37c55a8a", "at": "...", "subject": "Add 20 agents...",
#               "total": 223, "added": ["Kedro", ...], "removed": [], "edited": []}],
#  "metadata": {"count": 50, "total": 32}}
```

Built from git by `changelog.py` and served from `data/changelog.json`, rather
than computed per request: the web process may not have a working tree, and
the history only changes when the catalogue does. An absent file is an empty
history, which is the truthful answer before the generator has ever run.

Edits are reported per field, so a re-categorisation and a rewritten
description are distinguishable. Star counts are deliberately excluded — a bot
refreshes them weekly, and including them would bury every addition under a
wall of numbers.

## List technologies

```bash
GET /api/tech
# [{"name": "Python", "count": 26}, {"name": "TypeScript", "count": 10}]
```

Agent records store `stack` as one comma-joined string (FAISS metadata values
must be scalars); this endpoint splits it back into individual technologies.

## Statistics

```bash
GET /api/stats
# {"count": 106, "categories": 12, "top_category": {"name": "Code Generation", "count": 9},
#  "total_stars": 653000, "average_stars": 17648, "embedding_model": "nomic-embed-text",
#  "built_at": "2026-08-06T20:48:31+00:00"}
```

## Health

```bash
GET /api/health
```

Returns `200` when the index is usable, and `503` with a `detail` explaining why
when it is not — unseeded, unreachable, or built by a different embedding model.
The payload also reports `index_built_at`, so you can tell whether the index
predates your current `agents.json`.

## Proposing an agent

Public, unlike the editing endpoints below. A submission is only a proposal:
it is validated with the same rules as a direct edit, then queued. Nothing
reaches the catalogue until a maintainer approves it, so the write path stays
as restricted as it was.

```bash
POST /api/submissions
Content-Type: application/json

{
  "name": "Your Agent",
  "description": "One or two sentences on what it does.",
  "category": "Automation",
  "tech_stack": ["Python"],
  "github_stars": 1000,
  "url": "https://github.com/owner/repo",
  "use_case": "The specific job it is good at"
}
```

Returns `202` with an id and `status: "pending"`. A name already in the
catalogue — or already proposed and awaiting review — is rejected up front
rather than queued for someone to discover later.

Rate limited by `RATE_LIMIT_SUBMISSIONS` (default 10/minute), tighter than
search: this is public and writes to disk. Set `ENABLE_SUBMISSIONS=false` to
close the queue.

Because the endpoint is public, every dimension the caller controls is bounded:

| Bound | Default | On breach |
| --- | --- | --- |
| Request body | `MAX_REQUEST_BYTES` = 64 KiB | `413` with `max_bytes` |
| `name` / `category` | 80 / 60 characters | `400` |
| `description` | 60–500 characters | `400` |
| `url` | 500 characters | `400` |
| `use_case` | 200 characters | `400` |
| `tech_stack` | 12 entries, 40 characters each | `400` |
| `status` | Ignored on `/api/submissions` | — |
| Pending queue | `MAX_PENDING_SUBMISSIONS` = 200 | `429` |

The field limits apply to `/api/admin` edits too — both paths share
`validate()`, so the catalogue cannot be given a record the queue would refuse.

`status` (`active`, `archived`, `dormant`) is the reverse: the editor may set
it, a submission may not. It is maintained by `audit.py` from what GitHub
reports and the review UI does not show it, so a proposer setting their own
health badge would sail past a reviewer. A submitted value is normalised to
`active` rather than refused, since a client echoing the whole record back is
not doing anything wrong.

The 60-character description minimum is the one rule the queue applies and the
editor does not. The description is what gets embedded, so a tagline retrieves
badly; a maintainer typing one directly is trusted (and CI has a guard), but an
approved submission would put an unusable record in the catalogue and break the
build for somebody else.

## Reviewing submissions

Requires `ENABLE_ADMIN=true`.

```bash
GET  /api/admin/submissions?status=pending      # pending | approved | rejected
POST /api/admin/submissions/<id>/approve        # adds it to the catalogue
POST /api/admin/submissions/<id>/reject         # optional {"note": "why"}
```

Approving goes through the same write path as a direct add — same validation,
lock and audit entry — so it cannot smuggle in a record a normal edit would
reject. If the catalogue moved on and the name is now taken, approval fails
with `409` and the proposal returns to pending rather than being consumed.

`GET /api/admin/status` reports `pending_submissions`.

## Catalogue editing

Requires `ENABLE_ADMIN=true`; every route returns 403 otherwise.

```bash
POST   /api/admin/agents           # add    (409 on a duplicate name)
PUT    /api/admin/agents/<name>    # edit   (404 if unknown)
DELETE /api/admin/agents/<name>    # remove
POST   /api/admin/reindex          # rebuild the index from the catalogue
POST   /api/admin/undo             # reverse the most recent change
POST   /api/admin/similar-check    # near-duplicates of a draft agent
GET    /api/admin/agents           # the catalogue as it is on disk
GET    /api/admin/audit            # recent changes, newest first
GET    /api/admin/status           # whether editing is on, and if the index is behind
```

Adding an agent runs the draft through the index first and warns if the
catalogue already has something very similar — an exact name is rejected
outright, but the same tool under a different name is easy to miss at a
hundred-plus entries. It is advisory; you can add anyway.

Every change is appended to an audit log (`data/catalogue_audit.jsonl`) with
the record as it was before, which is what makes undo possible — edits
overwrite `agents.json` in place, so without it a mistake would be
unrecoverable. The editor shows the recent trail and offers **Undo last
change**.

Writes are atomic, so an interrupted request cannot truncate `agents.json`.

## Machine-readable spec

```bash
GET /api/openapi.json
```

Generated from the live URL map rather than hand-written, so it cannot drift
from the routes that actually exist; summaries come from the handler
docstrings.

## Response headers

Every response carries a baseline security policy: a Content-Security-Policy
that disallows inline and third-party scripts (beyond the two CDNs the pages
use), plus `X-Content-Type-Options`, `Referrer-Policy`, `X-Frame-Options` and
`Permissions-Policy`. `X-Response-Time` reports server-side duration.
