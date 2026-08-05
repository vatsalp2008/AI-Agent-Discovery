"""Central configuration for the AI Agent Discovery backend.

Every module reads its settings from here so that environment handling and
path resolution happen exactly once. Paths are anchored to the repository
root rather than the current working directory, so the app behaves the same
whether it is started from the repo root, from ``ai-agent-discovery/``, or
from an editor.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# backend/config.py -> backend/ -> ai-agent-discovery/ -> repo root
PACKAGE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = PACKAGE_DIR.parent

load_dotenv(PACKAGE_DIR / ".env")


def _resolve(value: str, default: Path) -> Path:
    """Resolve a configured path, treating relative values as repo-relative."""
    if not value:
        return default
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return (REPO_ROOT / path).resolve()


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


DATA_DIR = _resolve(os.getenv("DATA_DIR", ""), REPO_ROOT / "data")
FAISS_DIR = _resolve(os.getenv("FAISS_DIR", ""), DATA_DIR / "faiss_index")
AGENTS_JSON = _resolve(os.getenv("AGENTS_JSON", ""), DATA_DIR / "agents.json")

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# Chat/generation model. Kept separate from the embedding model below: a chat
# model can produce embeddings, but a purpose-built embedding model is much
# faster and gives better retrieval quality.
MODEL_NAME = os.getenv("MODEL_NAME", "llama3.2")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")

SEARCH_DEFAULT_LIMIT = _int_env("SEARCH_DEFAULT_LIMIT", 10)
SEARCH_MAX_LIMIT = _int_env("SEARCH_MAX_LIMIT", 50)
MAX_QUERY_LENGTH = _int_env("MAX_QUERY_LENGTH", 500)

# Page size for GET /api/agents
AGENTS_PAGE_SIZE = _int_env("AGENTS_PAGE_SIZE", 50)
AGENTS_MAX_PAGE_SIZE = _int_env("AGENTS_MAX_PAGE_SIZE", 200)

# Number of recent search results to keep in memory. 0 disables caching.
SEARCH_CACHE_SIZE = _int_env("SEARCH_CACHE_SIZE", 128)

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


HOST = os.getenv("HOST", "127.0.0.1")
PORT = _int_env("PORT", 5000)

# Off by default: the Werkzeug debugger exposes an interactive console that
# can execute arbitrary code, so it must be opted into explicitly.
DEBUG = _bool_env("FLASK_DEBUG", False)

# Optional LLM summary of search results (the generation half of RAG).
# Requires MODEL_NAME to be pulled in Ollama; search works fine without it.
ENABLE_SUMMARY = _bool_env("ENABLE_SUMMARY", True)
SUMMARY_MAX_RESULTS = _int_env("SUMMARY_MAX_RESULTS", 5)
SUMMARY_MAX_TOKENS = _int_env("SUMMARY_MAX_TOKENS", 220)
SUMMARY_TIMEOUT = _float_env("SUMMARY_TIMEOUT", 30.0)
# Low but non-zero: summaries should be near-deterministic and stick to the
# retrieved context rather than embellish.
SUMMARY_TEMPERATURE = _float_env("SUMMARY_TEMPERATURE", 0.2)
