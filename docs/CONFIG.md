# Configuration

All settings are environment variables, read once in `backend/config.py`. Relative
paths resolve against the repository root, so commands work from any directory.

| Variable | Default | Purpose |
|----------|---------|---------|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server address |
| `EMBEDDING_MODEL` | `nomic-embed-text` | Model used to embed text |
| `MODEL_NAME` | `llama3.2` | Chat/generation model |
| `DATA_DIR` | `data` | Root for data files |
| `FAISS_DIR` | `data/faiss_index` | Where the index is persisted |
| `AGENTS_JSON` | `data/agents.json` | Agent catalogue |
| `SEARCH_DEFAULT_LIMIT` | `10` | Default result count |
| `SEARCH_MAX_LIMIT` | `50` | Upper bound on `limit` |
| `MAX_QUERY_LENGTH` | `500` | Longest accepted query |
| `AGENTS_PAGE_SIZE` | `50` | Default page size for `/api/agents` |
| `AGENTS_MAX_PAGE_SIZE` | `200` | Upper bound on that page size |
| `SEARCH_CACHE_SIZE` | `128` | Cached searches; `0` disables |
| `SEARCH_MIN_SCORE` | `0.5` | Below this, results are flagged as weak matches |
| `COMPARE_MAX_AGENTS` | `8` | Upper bound on `/api/compare` |
| `EMBEDDING_CACHE_SIZE` | `500` | Query embeddings kept on disk; `0` disables |
| `EMBEDDING_CACHE_PATH` | `data/embedding_cache.json` | Where they are stored |
| `ENABLE_ADMIN` | `false` | Catalogue editing — see the warning above |
| `DUPLICATE_SCORE` | `0.75` | Similarity above which a draft is flagged as a duplicate |
| `AUDIT_LOG_PATH` | `data/catalogue_audit.jsonl` | Record of catalogue edits |
| `LOG_FORMAT` | `text` | `text` or `json` (one object per line) |
| `HOST` / `PORT` | `127.0.0.1` / `5000` | Bind address |
| `FLASK_DEBUG` | `false` | Werkzeug debugger — see warning below |
| `RATE_LIMIT_SEARCHES` | `60` | Searches per minute per client; `0` disables |
| `RATE_LIMIT_SUMMARIES` | `20` | Summaries per minute per client; `0` disables |
| `ENABLE_SUMMARY` | `true` | Allow LLM-generated overviews |
| `SUMMARY_MAX_RESULTS` | `5` | Results sent to the chat model |
| `SUMMARY_MAX_TOKENS` | `220` | Length cap on a generated overview |
| `SUMMARY_TIMEOUT` | `30.0` | Seconds before generation is abandoned |
| `SUMMARY_TEMPERATURE` | `0.2` | Sampling temperature for overviews |
| `SLOW_REQUEST_MS` | `1000` | Requests at/above this are logged as slow |
| `LOG_LEVEL` | `INFO` | Logging verbosity |

> ⚠️ **Never enable `FLASK_DEBUG` on anything reachable by others.** The Werkzeug
> debugger exposes an interactive console that can execute arbitrary code.
