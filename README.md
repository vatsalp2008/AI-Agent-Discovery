# AI Agent Discovery

A **privacy-first, semantic search engine** for discovering AI agents and tools. Built with modern AI/ML technologies including RAG (Retrieval-Augmented Generation), vector embeddings, and local LLMs.

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.10+-green.svg)

## 🌟 Overview

AI Agent Discovery helps developers and researchers find the right AI agents for their needs using natural language queries. Instead of keyword matching, it uses semantic search powered by embeddings and vector databases to understand intent and return the most relevant results.

**Key Highlights:**
- 🔒 **100% Local & Private** - All embeddings and vector storage run locally using Ollama
- 🧠 **Semantic Search** - Natural language queries like "I need an agent to write Python code"
- 🎯 **Relevance Scored** - Every result carries a 0–1 score derived from vector distance
- 💬 **AI Overviews** - An optional local LLM explains which result fits your need, grounded only in what was retrieved
- 🎨 **Modern UI** - Clean, dark-themed interface inspired by developer tools
- 📊 **Rich Agent Database** - Curated collection of 60 AI agents and frameworks

## 🚀 Features

### Intelligent Search
- **Natural Language Queries**: Describe what you need in plain English
- **Semantic Understanding**: Goes beyond keyword matching to understand intent
- **Relevance Ranking**: Results ranked by similarity using vector embeddings
- **Category Filtering**: Restrict results to Code Generation, Research, Automation, etc.
- **AI Overviews**: A local chat model summarizes why the top results match, using only the retrieved agents
- **Shareable Searches**: The query and filter live in the URL, so results can be bookmarked and shared
- **Result Caching**: Repeat queries are served from memory instead of re-embedding

### Privacy-Focused Architecture
- **Local LLM**: Powered by Ollama
- **Local Vector Store**: FAISS-based vector database stored locally
- **No Cloud Dependencies**: All processing happens on your machine
- **No Data Leaks**: Your queries never leave your computer

### Developer-Friendly
- **REST API**: Clean, JSON-only API endpoints for integration
- **CLI**: Search the index from the terminal without starting the server
- **Accessible**: Keyboard-operable filters, labelled controls, and live-announced results
- **JSON Data Format**: Easy to extend with your own agents
- **Docker**: One command brings up Ollama, seeding, and the app
- **Tested**: Python and frontend suites run in seconds without Ollama or FAISS installed

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Python 3.10+, Flask |
| **AI/ML** | LangChain, Ollama, FAISS |
| **Frontend** | HTML5, CSS3, Vanilla JavaScript |
| **Testing** | pytest, vitest + jsdom, ruff |
| **Data** | JSON, Vector Store (FAISS) |
| **Embeddings** | `nomic-embed-text` via Ollama (local) |

## 📋 Prerequisites

- **Python 3.10 or higher**
- **[Ollama](https://ollama.ai)** - For local inference
- **Git**

Or just **Docker**, which handles all of the above.

## 🔧 Installation & Setup

### Option A: Docker (quickest)

```bash
git clone https://github.com/vatsalp2008/AI-Agent-Discovery.git
cd AI-Agent-Discovery
make docker-up
```

This starts Ollama, pulls the embedding model, seeds the index, and serves the
app on **http://localhost:5000**.

### Option B: Local install

**1. Clone the repository**

```bash
git clone https://github.com/vatsalp2008/AI-Agent-Discovery.git
cd AI-Agent-Discovery
```

**2. Install Ollama & pull the models**

```bash
# Install Ollama from https://ollama.ai, then:
ollama pull nomic-embed-text   # embeddings
ollama pull llama3.2           # chat model
```

**3. Set up the Python environment**

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
make install                      # or: pip install -r ai-agent-discovery/requirements-dev.txt
```

**4. Configure environment variables (optional)**

Defaults work out of the box. To customise, copy the template:

```bash
cp ai-agent-discovery/.env.example ai-agent-discovery/.env
```

**5. Seed the index**

```bash
make seed        # or: python ai-agent-discovery/seed.py
```

**6. Run the application**

```bash
make run         # or: python ai-agent-discovery/frontend/app.py
```

The application starts on **http://localhost:5000**.

## ⚙️ Configuration

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
| `COMPARE_MAX_AGENTS` | `4` | Upper bound on `/api/compare` |
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

## 🎯 Usage

### Pages

| Path | What it does |
|------|--------------|
| `/` | Search, with category chips, recent queries and export |
| `/dashboard` | Every agent, filterable and sortable, with totals |
| `/agent/<name>` | One agent in detail, plus similar agents |
| `/compare?names=A,B` | Agents side by side |

### Web Interface

1. Open `http://localhost:5000`
2. Browse the agent previews, or enter a natural language query:
   - "I need an agent to write Python code"
   - "Find me a tool for automating workflows"
3. Click a category chip to restrict results to that category
4. Click an agent's name for its detail page, with similar agents
5. Use **Copy link** to share a search — the query and category live in the
   URL, so results are bookmarkable and survive the Back button
6. **Export CSV / JSON** to take a result set elsewhere
7. Recent queries are remembered locally; they never leave your machine
8. Toggle light/dark in the header — the choice is saved, and the OS
   preference is honoured until you set one

Keyboard: <kbd>/</kbd> or <kbd>s</kbd> focuses search, <kbd>?</kbd> shows the
shortcut help, <kbd>Esc</kbd> closes it.

Everything is keyboard operable: the category chips are real buttons, the
results region announces updates, and a failed search offers a focused
**Try again** rather than making you retype.

### Command Line

```bash
python ai-agent-discovery/cli.py "an agent that writes python"
python ai-agent-discovery/cli.py "chatbot" --category "Customer Service" --limit 3
python ai-agent-discovery/cli.py --list
python ai-agent-discovery/cli.py --stats

# Filter and sort the catalogue
python ai-agent-discovery/cli.py --list --sort stars          # name | stars | category
python ai-agent-discovery/cli.py --list --tech Python --category "Code Generation"
python ai-agent-discovery/cli.py --tech-list                  # technologies with counts

# Drop weak matches instead of showing the closest guesses
python ai-agent-discovery/cli.py "banana bread" --min-score 0.5

# AI overview of the results, and machine-readable output
python ai-agent-discovery/cli.py "rag pipeline" --summarize
python ai-agent-discovery/cli.py "rag pipeline" --json | jq '.results[].name'
```

Run `--help` for the full list.

### API Endpoints

Every endpoint returns JSON, including errors.

#### Search agents

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
      "score": 0.7042
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

#### List agents (paginated, filterable, sortable)

```bash
GET /api/agents?limit=20&offset=0
GET /api/agents?category=Code%20Generation      # case-insensitive
GET /api/agents?tech=Python                     # matches whole stack entries
GET /api/agents?q=cursor                        # substring of name or description
GET /api/agents?sort=stars                      # name | stars | category
GET /api/agents?sort=name&order=desc            # asc | desc
```

```json
{
  "agents": [ { "name": "Aider", "description": "...", "metadata": { } } ],
  "metadata": {
    "total": 60, "count": 20, "limit": 20, "offset": 0,
    "category": null, "tech": null, "q": null, "sort": "name", "order": "asc",
    "has_more": true
  }
}
```

`sort=stars` defaults to descending, the others to ascending. Filters combine.
`q` is plain substring matching, deliberately not semantic: it answers "find
the agent I can already name", which vector search handles poorly for short
literal strings.

#### Get a single agent

```bash
GET /api/agents/Cursor      # case-insensitive; 404 if unknown
```

#### List categories

```bash
GET /api/categories
# [{"name": "Code Generation", "count": 6}, {"name": "Research", "count": 4}]
```

#### Similar agents

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

#### Compare agents

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
`COMPARE_MAX_AGENTS`.

#### List technologies

```bash
GET /api/tech
# [{"name": "Python", "count": 26}, {"name": "TypeScript", "count": 10}]
```

Agent records store `stack` as one comma-joined string (FAISS metadata values
must be scalars); this endpoint splits it back into individual technologies.

#### Statistics

```bash
GET /api/stats
# {"count": 60, "categories": 7, "top_category": {"name": "Code Generation", "count": 9},
#  "total_stars": 653000, "average_stars": 17648, "embedding_model": "nomic-embed-text",
#  "built_at": "2026-08-06T20:48:31+00:00"}
```

#### Health

```bash
GET /api/health
```

Returns `200` when the index is usable, and `503` with a `detail` explaining why
when it is not — unseeded, unreachable, or built by a different embedding model.
The payload also reports `index_built_at`, so you can tell whether the index
predates your current `agents.json`.

#### Response headers

Every response carries a baseline security policy: a Content-Security-Policy
that disallows inline and third-party scripts (beyond the two CDNs the pages
use), plus `X-Content-Type-Options`, `Referrer-Policy`, `X-Frame-Options` and
`Permissions-Policy`. `X-Response-Time` reports server-side duration.

## 📁 Project Structure

```
AI-Agent-Discovery/
├── ai-agent-discovery/
│   ├── backend/
│   │   ├── api.py              # Flask routes and request validation
│   │   ├── config.py           # Environment and path resolution
│   │   ├── embeddings.py       # Ollama embeddings client
│   │   ├── logging_setup.py    # Shared logging configuration
│   │   ├── generation.py       # Optional LLM overview (the RAG step)
│   │   ├── models.py           # Agent dataclass
│   │   ├── rate_limit.py       # Per-client request budgets
│   │   ├── request_log.py      # Per-request timing
│   │   ├── scoring.py          # Distance to relevance score
│   │   ├── scraper.py          # Sample data and catalogue loading
│   │   ├── security.py         # CSP and other response headers
│   │   └── vectorstore.py      # FAISS index, search, caching
│   ├── frontend/
│   │   ├── app.py              # Flask application entry point
│   │   ├── static/css/style.css
│   │   ├── static/img/favicon.svg
│   │   ├── static/js/agent-card.js      # Shared card rendering
│   │   ├── static/js/search-state.js    # URL state and request shaping
│   │   ├── static/js/dashboard-stats.js # Stat formatting
│   │   ├── static/js/main.js            # Search page
│   │   ├── static/js/dashboard.js       # Dashboard page
│   │   ├── static/js/agent.js           # Agent detail page
│   │   ├── static/js/compare.js         # Comparison page
│   │   ├── static/js/theme.js           # Light/dark switching
│   │   ├── static/js/shortcuts.js       # Keyboard shortcuts
│   │   ├── static/js/recent-searches.js # Local query history
│   │   ├── static/js/export-results.js  # CSV and JSON export
│   │   └── templates/          # base, index, dashboard, agent, compare
│   ├── .env.example            # Configuration template
│   ├── cli.py                  # Terminal search tool
│   ├── refresh_stars.py        # Star count refresh
│   ├── requirements.txt        # Runtime dependencies
│   ├── requirements-dev.txt    # Plus pytest and ruff
│   └── seed.py                 # Index building script
├── data/
│   ├── agents.json             # Agent catalogue (source of truth)
│   └── faiss_index/            # Vector store (generated, gitignored)
├── tests/                      # Python test suite (pytest)
├── tests-js/                   # Frontend test suite (vitest + jsdom)
├── tests-live/                 # End-to-end tests against a real Ollama
├── .pre-commit-config.yaml
├── CONTRIBUTING.md
├── Dockerfile
├── docker-compose.yml
├── Makefile
└── README.md
```

## 🔍 How It Works

### Architecture Overview

```mermaid
graph LR
    A[User Query] --> B[Flask API]
    B --> C[Ollama Embeddings]
    C --> D[FAISS Vector Store]
    D --> E[Semantic Search]
    E --> F[Ranked Results]
    F --> G[JSON Response]
    G --> H[Web UI]
    F -. optional .-> I[Chat Model]
    I -. grounded overview .-> G
```

### Retrieval-augmented generation

Retrieval and generation are deliberately separate. FAISS retrieves candidate
agents; the chat model is then given **only those agents** and asked to compare
them against what the user wanted. The prompt tells it to use nothing else and
not to invent tools or numbers, which keeps a small local model useful and
limits invention.

The web UI requests results first and the overview second, so you never wait on
the model to see your results. The second request re-uses the cached retrieval,
so it only pays for generation.

Generation never blocks retrieval: `backend/generation.py` returns `None` on any
failure. Set `ENABLE_SUMMARY=false` to turn it off entirely, in which case the
chat model is never contacted and `llama3.2` is not needed at all.

### Search Flow

1. **User Input**: User enters a natural language query
2. **Cache Check**: Identical recent queries return immediately
3. **Embedding Generation**: The query is converted to a vector using Ollama
4. **Vector Search**: FAISS finds the nearest agent embeddings
5. **Scoring & Filtering**: Distances become scores; category filters are applied
6. **Response**: Top results are returned with metadata
7. **Overview (optional)**: The retrieved agents are passed to the chat model,
   which writes a short grounded comparison

### Data Pipeline

1. **Seed Phase**: `seed.py` loads agents from `data/agents.json`
2. **Embedding**: Each agent description is embedded using Ollama
3. **Indexing**: Vectors are stored in the FAISS index, alongside an
   `index_meta.json` recording which embedding model built it
4. **Query**: User queries are embedded and matched against the index

Re-running `seed.py` **rebuilds** the index rather than appending, so repeated
runs are idempotent. Pass `--append` to add to an existing index instead.

## 🎨 Customization

### Adding Your Own Agents

`data/agents.json` is the source of truth — `seed.py` reads it and writes it
back, so your edits are preserved.

```json
{
  "name": "Your Agent",
  "description": "What it does...",
  "category": "Code Generation",
  "tech_stack": ["Python", "GPT-4"],
  "github_stars": 1000,
  "url": "https://github.com/...",
  "use_case": "Specific use case"
}
```

Then rebuild the index:

```bash
make seed
```

Unknown fields are ignored, so you can annotate records freely. If the file
is malformed, `seed.py` names the offending entry and exits non-zero rather
than failing with a traceback:

```
error: data/agents.json is not valid JSON: Illegal trailing comma before end
of object (line 1, column 19)
```

### Changing the Embedding Model

```bash
ollama pull mxbai-embed-large
echo "EMBEDDING_MODEL=mxbai-embed-large" >> ai-agent-discovery/.env
make seed        # required: vectors from one model are unusable by another
```

If you forget to re-seed, the app detects the mismatch and `/api/health`
reports it rather than returning nonsense results.

### Customizing the UI

- **Styles**: `ai-agent-discovery/frontend/static/css/style.css`
- **Shared layout**: `ai-agent-discovery/frontend/templates/base.html`
- **Pages**: `templates/index.html`, `dashboard.html`, `agent.html`
- **Card rendering**: `ai-agent-discovery/frontend/static/js/agent-card.js`
- **Search behaviour**: `ai-agent-discovery/frontend/static/js/main.js`
- **Response headers / CSP**: `ai-agent-discovery/backend/security.py`

Adding an inline `<script>` will be blocked by the Content-Security-Policy —
put it in a file under `static/js/` instead.

## 🧪 Development

```bash
make help          # list every target
make check         # lint + Python tests + frontend tests, as CI runs them
make test          # Python only
make test-js       # frontend only (needs: make install-js)
make test-live     # end-to-end against a real Ollama + seeded index
make lint
make fix           # apply autofixable lint findings
make refresh-stars # update GitHub star counts in data/agents.json
make clean         # drop caches and the generated index
```

The Python suite stubs out langchain and Ollama; the frontend suite runs in
jsdom. Neither needs a model installed, and both finish in seconds.

`make test-live` is separate and **not** part of `make check`: it exercises the
real embedding and chat models to catch what stubs cannot — that embeddings are
unit vectors, that scores actually separate relevant from irrelevant results,
and that generated overviews only mention agents that were actually retrieved.
It needs a running Ollama and a seeded index, and skips cleanly without them.

A separate scheduled workflow refreshes GitHub star counts weekly and opens a
pull request with the changes.

**CI** runs three jobs: the Python checks on 3.10 and 3.12, the frontend suite,
and a `live` job that starts an Ollama service container, pulls both models and
runs `tests-live` for real. That last job asserts the suite did not skip itself,
so a broken setup fails loudly instead of passing silently.

### Pre-commit hooks

```bash
pip install pre-commit
pre-commit install
```

Runs the same lint and tests CI does, plus whitespace and JSON checks and a
guard against committing the FAISS index (it is a pickle, and regenerable with
`make seed`). Every hook is `language: system`, so they use this project's
environment rather than a separately pinned copy that could disagree with
`requirements-dev.txt`.

See [CONTRIBUTING.md](CONTRIBUTING.md) for conventions and setup details.

### Testing the API

```bash
curl -X POST http://localhost:5000/api/search \
  -H "Content-Type: application/json" \
  -d '{"query": "code generation agent", "limit": 3}'

# With an AI overview (requires the chat model to be pulled)
curl -X POST http://localhost:5000/api/search \
  -H "Content-Type: application/json" \
  -d '{"query": "code generation agent", "limit": 3, "summarize": true}'

curl "http://localhost:5000/api/agents?limit=5"
curl "http://localhost:5000/api/agents?sort=stars&tech=Python"
curl http://localhost:5000/api/agents/Cursor
curl http://localhost:5000/api/categories
curl http://localhost:5000/api/tech
curl http://localhost:5000/api/stats
curl http://localhost:5000/api/health
```

## 🤝 Contributing

Contributions are welcome:

1. **Add More Agents**: Expand `data/agents.json`
2. **Improve Search**: Enhance ranking and filtering
3. **UI Enhancements**: Make the interface even better
4. **Documentation**: Improve docs and examples

Read [CONTRIBUTING.md](CONTRIBUTING.md) first, and make sure `make check` passes
before opening a pull request.

### Contribution Workflow

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **Ollama** - For making local LLMs accessible
- **LangChain** - For the excellent LLM framework
- **FAISS** - For efficient vector similarity search
- **AI Agent Community** - For building amazing tools

## 📧 Contact

For questions or feedback, please open an issue on GitHub.

---

**Built with ❤️ for the AI agent community**
