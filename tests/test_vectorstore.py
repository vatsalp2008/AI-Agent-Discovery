import json

import pytest

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


def test_a_failed_rebuild_keeps_the_previous_index(store, agents, monkeypatch):
    """An Ollama outage mid-rebuild must not strand the app with no index."""
    import vectorstore as vectorstore_module

    before = len(store.search("agent"))
    assert before > 0

    def explode(*args, **kwargs):
        raise RuntimeError("ollama down")

    monkeypatch.setattr(vectorstore_module, "_faiss",
                        lambda: type("F", (), {"from_documents": staticmethod(explode)}))

    with pytest.raises(RuntimeError):
        store.replace_agents(agents)

    assert len(store.search("agent")) == before, "previous index was lost"


def test_a_successful_rebuild_replaces_the_index(store, agents):
    store.replace_agents(agents)
    assert store.vector_store is not None
    assert len(store.get_all_agents()) == len(agents)


class TestExactNameMatching:
    """A product named after an ordinary word cannot be found by similarity.

    Searching "Evidently" did not return the tool called Evidently anywhere in
    the top ten — the bare adverb reads as generic English.
    """

    def test_an_exact_name_is_ranked_first(self, store):
        results = store.search("GPT Researcher", limit=3)
        assert results[0]["name"] == "GPT Researcher"
        assert results[0]["match"] == "name"

    def test_matching_is_case_insensitive(self, store):
        assert store.search("gpt researcher", limit=3)[0]["name"] == "GPT Researcher"

    def test_surrounding_whitespace_is_ignored(self, store):
        assert store.search("  Cursor  ", limit=3)[0]["name"] == "Cursor"

    def test_a_substring_does_not_hoist(self, store):
        """"Code" must not hijack the ranking for "Claude Code"."""
        results = store.search("Cur", limit=3)
        assert all(r["match"] == "semantic" for r in results)

    def test_ordinary_queries_keep_score_order(self, store):
        results = store.search("agent", limit=3)
        assert [r["score"] for r in results] == sorted((r["score"] for r in results), reverse=True)
        assert all(r["match"] == "semantic" for r in results)

    def test_the_limit_is_still_respected(self, store):
        assert len(store.search("Cursor", limit=1)) == 1

    def test_an_unknown_name_changes_nothing(self, store):
        results = store.search("NoSuchAgentAnywhere", limit=3)
        assert all(r["match"] == "semantic" for r in results)

    def test_a_name_match_is_labelled_not_disguised(self, store):
        """Reporting 1.0 as a similarity score would be misleading."""
        result = store.search("Cursor", limit=1)[0]
        assert result["match"] == "name"
        assert result["score"] == 1.0

    def test_it_does_not_duplicate_an_agent_already_returned(self, store):
        results = store.search("Cursor", limit=5)
        assert [r["name"] for r in results].count("Cursor") == 1


def test_a_name_match_scores_the_same_either_way(store, weak_store):
    """Whether the vector search happened to return the agent is an accident
    of retrieval; it must not change the score the caller sees."""
    result = weak_store.search("Cursor", limit=3)[0]
    assert result["match"] == "name"
    assert result["score"] == 1.0


def test_min_score_never_drops_an_agent_asked_for_by_name(weak_store):
    results = weak_store.search("Cursor", limit=3, min_score=0.9)
    assert [r["name"] for r in results] == ["Cursor"]
