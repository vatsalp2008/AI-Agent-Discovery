import json

from vectorstore import VectorStore


def test_search_ranks_by_descending_score(store):
    results = store.search("agent", limit=3)
    assert [r["score"] for r in results] == sorted((r["score"] for r in results), reverse=True)
    assert results[0]["score"] == 1.0  # distance 0


def test_search_overfetches_when_filtering_by_category(store):
    store.search("agent", limit=2, category="Research")
    assert store.vector_store.last_k == 2 * VectorStore.CATEGORY_OVERFETCH


def test_category_filter_is_case_insensitive(store):
    assert store.search("agent", category="code generation")
    assert store.search("agent", category="CODE GENERATION")


def test_unknown_category_returns_nothing(store):
    assert store.search("agent", category="Nonexistent") == []


def test_search_never_exceeds_the_limit(store):
    assert len(store.search("agent", limit=1, category="Code Generation")) == 1


def test_search_on_an_empty_store_returns_nothing(tmp_path):
    vs = VectorStore(persist_directory=tmp_path / "index", embedding_function=object())
    assert vs.vector_store is None
    assert vs.search("anything") == []


def test_an_unseeded_store_reports_consistently_empty_stats(tmp_path):
    """count must not disagree with the rest of the summary."""
    vs = VectorStore(persist_directory=tmp_path / "index", embedding_function=object())
    stats = vs.get_stats()
    assert stats["count"] == 0
    assert stats["categories"] == 0
    assert stats["top_category"] is None
    assert stats["total_stars"] == 0
    assert stats["average_stars"] == 0


def test_an_unseeded_store_does_not_serve_the_raw_json_catalogue(tmp_path, agents_json):
    vs = VectorStore(persist_directory=tmp_path / "index", embedding_function=object())
    assert vs.get_all_agents() == []
    assert vs.get_categories() == []


def test_get_all_agents_is_sorted_by_name(store):
    names = [a["name"] for a in store.get_all_agents()]
    assert names == sorted(names, key=str.lower)


def test_get_categories_orders_by_count_then_name(store):
    assert store.get_categories() == [
        {"name": "Code Generation", "count": 2},
        {"name": "Research", "count": 1},
    ]


def test_falls_back_to_json_when_the_docstore_is_unreadable(store, agents_json):
    """A changed FAISS internal layout must not look like an empty index."""
    del store.vector_store.docstore._dict  # force AttributeError
    store.vector_store.docstore = object()

    agents = store.get_all_agents()
    assert [a["name"] for a in agents] == ["Aider", "Cursor", "GPT Researcher"]


def test_json_fallback_survives_a_corrupt_file(store, agents_json):
    store.vector_store.docstore = object()
    agents_json.write_text("{ not valid json")
    assert store.get_all_agents() == []


def test_json_fallback_tolerates_unknown_fields(store, agents_json):
    store.vector_store.docstore = object()
    records = json.loads(agents_json.read_text())
    records[0]["added_by"] = "someone"
    agents_json.write_text(json.dumps(records))
    assert len(store.get_all_agents()) == 3


def test_add_agents_ignores_an_empty_list(store):
    before = store.vector_store
    store.add_agents([])
    assert store.vector_store is before


def test_search_returns_the_plain_description_not_the_embedded_blob(store):
    """The frontend used to strip 'Description: ' back out of page_content."""
    result = store.search("agent", limit=1)[0]
    assert result["description"] == "AI-powered code editor."
    assert "Name:" not in result["description"]


def test_search_still_exposes_the_embedded_text(store):
    """The composite text that was actually embedded stays available."""
    result = store.search("agent", limit=1)[0]
    assert result["matched_text"].startswith("Name: Cursor")
    assert "Tech Stack:" in result["matched_text"]


def test_agent_list_is_built_once(store):
    """/api/stats alone used to rebuild it twice per request."""
    calls = []
    original = store._build_agents
    store._build_agents = lambda: (calls.append(1), original())[1]

    store.get_all_agents()
    store.get_all_agents()
    store.get_categories()
    store.get_stats()
    assert len(calls) == 1


def test_reindexing_rebuilds_the_agent_list(store, agents):
    before = len(store.get_all_agents())
    store.add_agents(agents)
    assert len(store.get_all_agents()) == before + len(agents)


def test_agent_lookup_uses_an_index(store):
    store.get_agent("Cursor")
    assert store._agents_by_name is not None
    assert set(store._agents_by_name) == {"cursor", "aider", "gpt researcher"}


def test_agent_lookup_index_is_invalidated_on_reindex(store, agents):
    assert store.get_agent("Cursor") is not None
    store.add_agents(agents)
    assert store._agents_by_name is None
    assert store.get_agent("Cursor") is not None


def test_callers_cannot_mutate_the_cached_agent_list(store):
    first = store.get_all_agents()
    first.clear()
    assert len(store.get_all_agents()) == 3
