"""End-to-end tests against a real Ollama server.

The rest of the suite stubs langchain and Ollama so it runs anywhere in
milliseconds. That is the right default, but it cannot catch problems that
only appear against real models: wrong distance semantics, a prompt the chat
model ignores, or a timeout that is too tight.

These are skipped unless the pieces are actually present, so `make check`
behaves the same as before. Run them deliberately with:

    ollama pull nomic-embed-text
    ollama pull llama3.2
    pip install -r ai-agent-discovery/requirements.txt
    python ai-agent-discovery/seed.py
    make test-live

They live outside tests/ because they load the real langchain stack, which
tests/conftest.py replaces with stubs.
"""

import math
import os
import urllib.error
import urllib.request

import pytest

OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")


def _ollama_models():
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=3) as response:
            import json
            return {m["name"].split(":")[0] for m in json.load(response).get("models", [])}
    except (urllib.error.URLError, OSError, ValueError):
        return set()


AVAILABLE = _ollama_models()

needs_embeddings = pytest.mark.skipif(
    "nomic-embed-text" not in AVAILABLE,
    reason="requires Ollama with nomic-embed-text pulled",
)
needs_chat = pytest.mark.skipif(
    "llama3.2" not in AVAILABLE,
    reason="requires Ollama with llama3.2 pulled",
)


@pytest.fixture(scope="module")
def live_store():
    """The real VectorStore over the real index."""
    pytest.importorskip("faiss", reason="requires faiss-cpu")
    pytest.importorskip("langchain_ollama", reason="requires langchain-ollama")

    import config
    from vectorstore import VectorStore

    if not os.path.exists(os.path.join(str(config.FAISS_DIR), "index.faiss")):
        pytest.skip("no seeded index; run seed.py first")

    store = VectorStore()
    if not store.vector_store:
        pytest.skip("index could not be loaded")
    return store


@needs_embeddings
def test_embeddings_are_unit_vectors():
    """scoring.relevance_score treats distance as cosine; that needs unit norms."""
    from embeddings import get_embeddings

    vector = get_embeddings().embed_query("a command line coding tool")
    norm = math.sqrt(sum(x * x for x in vector))
    assert norm == pytest.approx(1.0, abs=1e-3)


@needs_embeddings
def test_verbatim_description_finds_its_own_agent(live_store):
    results = live_store.search(
        "A command line tool that lets you pair program with GPT-3.5/4. "
        "Edits code in your local git repo.",
        limit=3,
    )
    assert results[0]["name"] == "Aider"
    assert results[0]["score"] > 0.85, "a verbatim match should score very high"


@needs_embeddings
def test_semantic_match_beats_keyword_overlap(live_store):
    """The query shares no words with the description it should match."""
    results = live_store.search("edit code from my shell without leaving it", limit=5)
    assert "Aider" in [r["name"] for r in results[:3]]


@needs_embeddings
def test_unrelated_query_scores_far_below_a_real_match(live_store):
    relevant = live_store.search("automate workflows between apps", limit=1)[0]
    nonsense = live_store.search("banana bread recipe", limit=1)[0]
    assert relevant["score"] - nonsense["score"] > 0.25, (
        "scores must separate relevant from irrelevant results"
    )


@needs_embeddings
def test_category_filter_holds_against_real_embeddings(live_store):
    results = live_store.search("agent", limit=5, category="Research")
    assert results
    assert {r["metadata"]["category"] for r in results} == {"Research"}


@needs_chat
@needs_embeddings
def test_generated_overview_is_grounded_in_the_results(live_store):
    """The prompt tells the model to use only the retrieved agents."""
    import generation

    query = "I need an agent that edits code in my terminal"
    results = live_store.search(query, limit=5)
    summary = generation.summarize(query, results)

    assert summary, "generation returned nothing against a real chat model"
    assert len(summary) > 40
    # It should name something it was actually given.
    assert any(r["name"].lower() in summary.lower() for r in results)


@needs_chat
@needs_embeddings
def test_generation_finishes_well_inside_the_timeout(live_store):
    import time

    import config
    import generation

    results = live_store.search("workflow automation", limit=5)
    start = time.perf_counter()
    summary = generation.summarize("workflow automation", results)
    elapsed = time.perf_counter() - start

    assert summary
    assert elapsed < config.SUMMARY_TIMEOUT, (
        f"generation took {elapsed:.1f}s against a {config.SUMMARY_TIMEOUT}s timeout"
    )


@needs_embeddings
def test_index_sidecar_matches_the_configured_model(live_store):
    import config

    assert live_store._read_meta().get("embedding_model") == config.EMBEDDING_MODEL
    assert live_store.stale_model is None


@needs_chat
@needs_embeddings
@pytest.mark.parametrize("query", [
    "agent that edits code in my terminal",
    "chat with my documents privately",
    "multi agent orchestration framework",
])
def test_overview_never_mentions_an_agent_it_was_not_given(live_store, query):
    """Mechanical grounding check.

    Naming a catalogue agent that was not among the retrieved results means the
    model reached outside its context — the failure mode the prompt guards
    against.
    """
    import re

    import generation

    results = live_store.search(query, limit=5)
    summary = generation.summarize(query, results)
    assert summary

    given = {r["name"] for r in results}
    catalogue = {a["name"] for a in live_store.get_all_agents()}
    leaked = {
        name for name in catalogue - given
        if re.search(rf"\b{re.escape(name)}\b", summary)
    }
    assert not leaked, f"summary mentioned agents it was not given: {sorted(leaked)}"
