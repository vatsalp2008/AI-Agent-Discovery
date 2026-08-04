"""Test fixtures.

The backend imports langchain/FAISS at module load and reaches out to Ollama
when a VectorStore is built. Neither is available (or desirable) in a unit
test run, so the heavy imports are stubbed here and the store is replaced
with an in-memory fake. What is left under test is our own logic: request
validation, scoring, filtering, and catalogue loading.
"""

import json
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND = REPO_ROOT / "ai-agent-discovery" / "backend"
sys.path.insert(0, str(BACKEND))


def _install_langchain_stubs():
    for name in (
        "langchain_community",
        "langchain_community.vectorstores",
        "langchain_core",
        "langchain_core.documents",
        "langchain_ollama",
    ):
        sys.modules.setdefault(name, types.ModuleType(name))

    class _Document:
        def __init__(self, page_content="", metadata=None):
            self.page_content = page_content
            self.metadata = metadata or {}

    class _OllamaEmbeddings:
        """Records how the real client would have been configured."""

        def __init__(self, base_url=None, model=None):
            self.base_url = base_url
            self.model = model

    sys.modules["langchain_community.vectorstores"].FAISS = object
    sys.modules["langchain_core.documents"].Document = _Document
    sys.modules["langchain_ollama"].OllamaEmbeddings = _OllamaEmbeddings

    # get_embeddings() would construct a real Ollama client.
    embeddings = types.ModuleType("embeddings")
    embeddings.get_embeddings = lambda: object()
    sys.modules["embeddings"] = embeddings


_install_langchain_stubs()

from models import Agent  # noqa: E402


AGENT_RECORDS = [
    {
        "name": "Cursor",
        "description": "AI-powered code editor.",
        "category": "Code Generation",
        "tech_stack": ["Electron", "GPT-4"],
        "github_stars": 35000,
        "url": "https://cursor.sh",
        "use_case": "Code editing",
    },
    {
        "name": "Aider",
        "description": "Pair program from the terminal.",
        "category": "Code Generation",
        "tech_stack": ["Python", "Git"],
        "github_stars": 12000,
        "url": "https://github.com/paul-gauthier/aider",
        "use_case": "Terminal pair programming",
    },
    {
        "name": "GPT Researcher",
        "description": "Autonomous online research agent.",
        "category": "Research",
        "tech_stack": ["Python", "LangChain"],
        "github_stars": 14000,
        "url": "https://github.com/assafelovic/gpt-researcher",
        "use_case": "Deep research",
    },
]


@pytest.fixture
def agents():
    return [Agent.from_dict(record) for record in AGENT_RECORDS]


@pytest.fixture
def agents_json(tmp_path):
    """A temporary data/agents.json, with config pointed at it."""
    import config

    path = tmp_path / "agents.json"
    path.write_text(json.dumps(AGENT_RECORDS, indent=2))

    original_dir, original_json = config.DATA_DIR, config.AGENTS_JSON
    config.DATA_DIR, config.AGENTS_JSON = tmp_path, path
    yield path
    config.DATA_DIR, config.AGENTS_JSON = original_dir, original_json


class FakeInnerStore:
    """Stands in for langchain's FAISS wrapper."""

    def __init__(self, documents):
        self.documents = documents
        self.docstore = types.SimpleNamespace(_dict=dict(enumerate(documents)))
        self.index = types.SimpleNamespace(ntotal=len(documents))
        self.last_k = None
        # Counts real lookups, so cache hits are observable.
        self.query_count = 0

    def add_documents(self, documents):
        self.documents.extend(documents)
        self.docstore._dict = dict(enumerate(self.documents))
        self.index.ntotal = len(self.documents)

    def save_local(self, path):
        pass

    def similarity_search_with_score(self, query, k):
        self.last_k = k
        self.query_count += 1
        # Deterministic ranking: index order, increasing distance.
        return [(doc, round(i * 0.5, 4)) for i, doc in enumerate(self.documents[:k])]


@pytest.fixture
def store(agents, tmp_path):
    """A VectorStore backed by the fake inner store (no Ollama, no FAISS)."""
    from langchain_core.documents import Document
    from vectorstore import VectorStore

    documents = [Document(page_content=a.page_content, metadata=a.metadata) for a in agents]
    vs = VectorStore(persist_directory=tmp_path / "index", embedding_function=object())
    vs.vector_store = FakeInnerStore(documents)
    return vs


@pytest.fixture
def client(store):
    """Flask test client wired to the fake store."""
    from flask import Flask

    import api

    api.set_store(store)
    app = Flask(__name__)
    app.register_blueprint(api.api_bp)
    api.register_error_handlers(app)
    with app.test_client() as test_client:
        yield test_client
    api.set_store(None)
