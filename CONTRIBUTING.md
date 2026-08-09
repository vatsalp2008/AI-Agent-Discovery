# Contributing

Thanks for your interest in AI Agent Discovery. This document covers how to get
set up, what the project expects from a change, and the conventions worth
knowing before you start.

## Getting set up

```bash
git clone https://github.com/vatsalp2008/AI-Agent-Discovery.git
cd AI-Agent-Discovery

python -m venv venv && source venv/bin/activate
make install          # Python runtime + dev dependencies
make install-js       # frontend test dependencies

make check            # lint + Python tests + frontend tests
```

`make check` needs no Ollama and no models: the Python suite stubs langchain
and the Ollama client, and the frontend suite runs in jsdom. It should finish
in a couple of seconds.

To run the app for real you additionally need [Ollama](https://ollama.ai):

```bash
ollama pull nomic-embed-text   # embeddings (required)
ollama pull llama3.2           # chat model (only for AI overviews)
make seed
make run
```

With that in place you can also run the end-to-end suite, which checks things
the stubs cannot — that embeddings are unit vectors, that scores separate
relevant from irrelevant results, and that generation stays grounded and inside
its timeout:

```bash
make test-live
```

It is deliberately outside `make check` and skips cleanly when Ollama or the
index is missing.

## Before opening a pull request

1. `make check` passes.
2. New behaviour has a test. Bug fixes should have a test that fails before
   the fix.
3. Commit messages are short and imperative ("Add category filtering", not
   "added category filtering and some other stuff").
4. Docs are updated if you changed the API surface, configuration, or setup.

CI runs the same checks on Python 3.10 and 3.12 plus the frontend suite, and a
`live` job that starts an Ollama container, seeds an index, drives the MCP
server, and runs `tests-live` for real.

`pre-commit install` runs the same lint and tests locally before each commit.

## Project conventions

**Configuration lives in one place.** Everything is an environment variable
read once in `backend/config.py`, which also resolves paths relative to the
repository root. Do not call `os.getenv` elsewhere, and do not build paths
relative to the current working directory — commands must work from anywhere.

**Agent data is untrusted.** `data/agents.json` is meant to be hand-edited, so
every field is attacker-controlled from the frontend's point of view. Cards are
built with DOM APIs and `textContent`, never `innerHTML` templates, and links
are restricted to absolute `http(s)` URLs. If you touch
`static/js/agent-card.js`, keep the escaping tests green.

**The vector store is built lazily.** Importing `api` must not contact Ollama.
This keeps the app startable when Ollama is down and keeps tests fast.

**Generation is optional and best-effort.** `backend/generation.py` returns
`None` on any failure rather than raising. A missing chat model, a timeout, or
an unreachable Ollama must never cost a user their search results.

**Errors under `/api` are JSON.** Route handlers should let unexpected
exceptions propagate; the app-level handler in `api.register_error_handlers`
logs the traceback and returns a generic message. Do not echo exception text
back to clients.

**Re-seeding rebuilds.** `seed.py` replaces the index rather than appending, and
treats `data/agents.json` as the source of truth so hand-edits survive.

**Writes are opt-in and validated.** `backend/admin.py` is the only module that
writes, and it is disabled unless `ENABLE_ADMIN=true`. It has no
authentication, so it must stay off by default and behind a localhost `HOST`.
Every write is atomic — write to a temporary file, then `os.replace` — so an
interrupted request cannot truncate `agents.json`.

**MCP tools are read-only.** `mcp_server.py` exposes search and lookup, never
mutation: an agent querying the catalogue should not be able to rewrite it.
Tool results are trimmed to the fields a caller needs, because everything sent
back costs the caller context.

**Cache what cannot go stale.** Search *results* depend on the index and are
invalidated whenever it changes. Query *embeddings* depend only on the model
and the text, so they are the thing persisted to disk
(`backend/embedding_cache.py`). Getting this backwards would serve results
from a catalogue that no longer exists.

**Keep imports off the startup path.** `langchain_community.vectorstores`
pulls in langsmith, roughly 300ms. Import it inside the function that needs it
(see `vectorstore._faiss`) rather than at module level, and measure with
`make benchmark` before and after.

**Pure logic goes in its own file.** Page scripts wrap everything in a
`DOMContentLoaded` closure, which makes it untestable. Helpers that do not touch
the DOM belong in a separate file with a global (`search-state.js`,
`dashboard-stats.js`) so `tests-js/` can exercise them directly.

## Adding agents to the catalogue

Edit `data/agents.json` and re-run `make seed`:

```json
{
  "name": "Your Agent",
  "description": "One or two sentences on what it does.",
  "category": "Code Generation",
  "tech_stack": ["Python", "GPT-4"],
  "github_stars": 1000,
  "url": "https://github.com/owner/repo",
  "use_case": "The specific job it is good at"
}
```

- `url` must be absolute; relative values are rejected and render as a disabled
  link.
- Unknown fields are ignored, so you can annotate records freely.
- Star counts go stale. Run `make refresh-stars` to update them from the GitHub
  API rather than editing the numbers by hand. Set `GITHUB_TOKEN` to avoid the
  60 requests/hour unauthenticated limit. A scheduled workflow also does this
  weekly and opens a pull request.
- **Verify the repository exists before adding it.** Check the URL against the
  GitHub API and take the description and star count from there. It is very
  easy to write a plausible entry for a project that does something else
  entirely; `tests/test_catalogue.py` cannot catch that.
- `tech_stack` entries must not contain commas — the field is stored
  comma-joined, so a comma would split one entry into two.
- Prefer `/admin` (with `ENABLE_ADMIN=true`) over hand-editing: it validates
  the record and explains what is wrong.

## Layout

| Path | What lives there |
|------|------------------|
| `ai-agent-discovery/backend/` | Config, API, vector store, embeddings, generation |
| `ai-agent-discovery/frontend/` | Flask entry point, templates, static assets |
| `ai-agent-discovery/cli.py` | Terminal search |
| `ai-agent-discovery/seed.py` | Index building |
| `ai-agent-discovery/refresh_stars.py` | Star count refresh |
| `ai-agent-discovery/mcp_server.py` | MCP server for other agents |
| `ai-agent-discovery/benchmark.py` | Hot-path measurements |
| `tests/` | Python tests (pytest) |
| `tests-js/` | Frontend tests (vitest + jsdom) |
| `tests-live/` | End-to-end tests against a real Ollama |

Run `make help` to see every available target.

## Reporting bugs

Please include what you ran, what you expected, and what happened. Output from
`curl localhost:5000/api/health` is usually the fastest way to identify setup
problems — it reports whether the index is usable and, if not, why.
