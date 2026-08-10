# AI Agent Discovery — application

This directory holds the application itself. For the full project overview,
configuration reference and API documentation, see the
[root README](../README.md).

## Layout

| Path | Purpose |
|------|---------|
| `backend/config.py` | Reads environment variables and resolves paths from the repo root |
| `backend/api.py` | Flask blueprint: routes, request validation, JSON error handlers |
| `backend/vectorstore.py` | FAISS index: loading, seeding, search, caching |
| `backend/embeddings.py` | Ollama embeddings client (via `langchain-ollama`) |
| `backend/models.py` | The `Agent` dataclass |
| `backend/scoring.py` | Converts FAISS distance to a 0–1 relevance score |
| `backend/generation.py` | Optional LLM overview of results (the generation half of RAG) |
| `backend/rate_limit.py` | Per-client request budgets for /api/search |
| `backend/security.py` | Content-Security-Policy and other response headers |
| `backend/admin.py` | Catalogue write API, disabled unless ENABLE_ADMIN=true |
| `backend/embedding_cache.py` | Query embeddings persisted between runs |
| `mcp_server.py` | MCP server exposing the index to other agents |
| `benchmark.py` | Hot-path measurements |
| `doctor.py` | Setup diagnostics: Ollama, models, catalogue, index |
| `backend/request_log.py` | Per-request timing |
| `backend/scraper.py` | Built-in sample agents and catalogue loading |
| `backend/logging_setup.py` | Shared logging configuration |
| `frontend/app.py` | Flask entry point |
| `frontend/templates/base.html` | Shared page shell: head, header, nav |
| `frontend/static/js/agent-card.js` | Card rendering shared by both pages |
| `frontend/static/js/search-state.js` | URL state and request shaping (unit tested) |
| `frontend/static/js/dashboard-stats.js` | Stat formatting and paging labels (unit tested) |
| `cli.py` | Terminal search tool |
| `refresh_stars.py` | Refreshes GitHub star counts from the API |
| `seed.py` | Builds the FAISS index |

## Quick start

`config.py` resolves paths from the repository root, so these work from any
directory:

```bash
ollama pull nomic-embed-text
pip install -r ai-agent-discovery/requirements-dev.txt
python ai-agent-discovery/seed.py
python ai-agent-discovery/frontend/app.py
```

Then open [http://localhost:5000](http://localhost:5000).

## Notes for contributors

- **Embeddings are separate from chat.** `EMBEDDING_MODEL` (default
  `nomic-embed-text`) generates vectors; `MODEL_NAME` is the chat model.
  Changing the embedding model invalidates the index — re-run `seed.py`. The
  app detects the mismatch and reports it via `/api/health` if you forget.
- **`data/agents.json` is the source of truth.** `seed.py` reads it and writes
  it back, so hand-edits survive. `SAMPLE_AGENTS` in `scraper.py` only
  bootstraps a fresh checkout.
- **Re-seeding rebuilds.** `seed.py` replaces the index rather than appending,
  so running it twice does not duplicate agents. Use `--append` to add instead.
- **Agent data is untrusted.** It is hand-edited JSON, so the frontend builds
  cards with DOM APIs and `textContent`, never `innerHTML` templates, and
  restricts links to `http(s)`.
- **The store is built lazily.** Importing `api` does not contact Ollama, so
  the app starts even when Ollama is down and tests need no models.
- **Generation is best-effort.** `generation.summarize` returns `None` on any
  failure. A missing chat model or a timeout must never cost a user their
  search results. Set `ENABLE_SUMMARY=false` to disable it entirely.
- **Scores are cosine similarity.** `scoring.relevance_score` converts the L2
  distance with `1 - d²/2`, which is exact only because these embedding models
  emit unit-length vectors. `tests-live/` asserts that property holds.
- **Keep page logic out of closures.** Pure helpers live in their own files
  (`search-state.js`, `dashboard-stats.js`) so they can be unit tested; the
  `DOMContentLoaded` handlers just wire them to the DOM.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/agents` | Agent list (`limit`, `offset`, `category`, `tech`, `q`, `min_stars`, `max_stars`, `sort`, `order`) |
| `GET` | `/api/agents/<name>` | Single agent, case-insensitive |
| `POST` | `/api/search` | Semantic search (`query`, `limit`, `category`, `min_score`, `summarize`) |
| `GET` | `/api/categories` | Categories with counts |
| `GET` | `/api/tech` | Technologies with counts |
| `GET` | `/api/stats` | Index summary, including `built_at` |
| `GET` | `/api/health` | Readiness probe; 503 when unusable |
| `GET` | `/api/agents/<name>/similar` | Neighbours of an agent, excluding itself |
| `GET` | `/api/compare?names=A,B` | Several agents at once |
| `POST` | `/api/admin/agents` | Add an agent (needs ENABLE_ADMIN) |
| `PUT` | `/api/admin/agents/<name>` | Edit an agent |
| `DELETE` | `/api/admin/agents/<name>` | Remove an agent |
| `POST` | `/api/admin/reindex` | Rebuild the index from the catalogue |
| `POST` | `/api/admin/undo` | Reverse the most recent catalogue change |
| `GET` | `/api/admin/audit` | Recent catalogue changes, newest first |
| `GET` | `/api/openapi.json` | Machine-readable API description |

Full request/response examples are in the [root README](../README.md).

## Tests

```bash
make check      # lint + Python tests + frontend tests, from the repo root
make test-live  # end-to-end against a real Ollama (needs a seeded index)
```

The Python suite stubs langchain and Ollama; the frontend suite runs in jsdom.
Neither needs a model installed. `make test-live` is the exception and is not
part of `make check`. See [CONTRIBUTING.md](../CONTRIBUTING.md).

## License

MIT — see [LICENSE](../LICENSE).
