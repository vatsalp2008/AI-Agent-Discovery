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

## Before opening a pull request

1. `make check` passes.
2. New behaviour has a test. Bug fixes should have a test that fails before
   the fix.
3. Commit messages are short and imperative ("Add category filtering", not
   "added category filtering and some other stuff").
4. Docs are updated if you changed the API surface, configuration, or setup.

CI runs the same checks on Python 3.10 and 3.12 plus the frontend suite.

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
  60 requests/hour unauthenticated limit.

## Layout

| Path | What lives there |
|------|------------------|
| `ai-agent-discovery/backend/` | Config, API, vector store, embeddings, generation |
| `ai-agent-discovery/frontend/` | Flask entry point, templates, static assets |
| `ai-agent-discovery/cli.py` | Terminal search |
| `ai-agent-discovery/seed.py` | Index building |
| `ai-agent-discovery/refresh_stars.py` | Star count refresh |
| `tests/` | Python tests (pytest) |
| `tests-js/` | Frontend tests (vitest + jsdom) |

Run `make help` to see every available target.

## Reporting bugs

Please include what you ran, what you expected, and what happened. Output from
`curl localhost:5000/api/health` is usually the fastest way to identify setup
problems — it reports whether the index is usable and, if not, why.
