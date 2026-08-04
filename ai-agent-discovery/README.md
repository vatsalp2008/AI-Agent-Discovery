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
| `backend/scraper.py` | Built-in sample agents and catalogue loading |
| `backend/logging_setup.py` | Shared logging configuration |
| `frontend/app.py` | Flask entry point |
| `frontend/static/js/agent-card.js` | Card rendering shared by both pages |
| `cli.py` | Terminal search tool |
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

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/agents` | Paginated agent list (`limit`, `offset`) |
| `GET` | `/api/agents/<name>` | Single agent, case-insensitive |
| `POST` | `/api/search` | Semantic search (`query`, `limit`, `category`) |
| `GET` | `/api/categories` | Categories with counts |
| `GET` | `/api/stats` | Index summary |
| `GET` | `/api/health` | Readiness probe; 503 when unusable |

Full request/response examples are in the [root README](../README.md).

## Tests

```bash
make check      # lint + tests, from the repo root
```

The suite stubs langchain and Ollama, so it runs without any models installed.

## License

MIT — see [LICENSE](../LICENSE).
