import json

import pytest

from vectorstore import VectorStore


def test_search_ranks_by_descending_score(store):
    results = store.search("agent", limit=3)
    assert [r["score"] for r in results] == sorted((r["score"] for r in results), reverse=True)
    assert results[0]["score"] == 1.0  # distance 0


def test_search_overfetches_when_filtering_by_category(store):
    """The nearest neighbours overall may all be in other categories, so a
    filtered search asks for more than it needs — but never for more than
    the index holds."""
    store.search("agent", limit=2, category="Research")
    expected = min(2 * VectorStore.CATEGORY_OVERFETCH, store.vector_store.index.ntotal)
    assert store.vector_store.last_k == expected


def _store_with(categories, tmp_path):
    """A store whose documents rank in the given category order.

    The shared `store` fixture holds three agents, which is fewer than the
    over-fetch would ask for — so every k collapses to the index size and a
    test written against it cannot tell the two behaviours apart.
    """
    from conftest import FakeInnerStore
    from langchain_core.documents import Document

    documents = [
        Document(page_content=f"agent number {i}",
                 metadata={"name": f"Agent{i}", "category": category, "description": ""})
        for i, category in enumerate(categories)
    ]
    vs = VectorStore(persist_directory=tmp_path / "index", embedding_function=object())
    vs.vector_store = FakeInnerStore(documents)
    return vs


def test_a_filtered_search_scans_the_whole_index(tmp_path):
    """The bug this guards, found by the live suite at 203 agents:
    search("agent", category="Research") returned nothing at all, because a
    fixed over-fetch of limit*5 covered a shrinking share of the catalogue as
    it grew. An empty category was reported for a category with members.

    Here the Research entries rank below the over-fetch window, so the old
    behaviour returns nothing and the fix returns them.
    """
    store = _store_with(["Other"] * 30 + ["Research"] * 10, tmp_path)

    results = store.search("agent", limit=3, category="Research")

    assert len(results) == 3, "a category with ten members answered with fewer"
    assert store.vector_store.last_k == 40


def test_a_filtered_search_embeds_the_query_once(store):
    """Filtering used to fetch a slice, find it short, then fetch again.
    The embedding is ~91% of a search, so that doubled the cost of nearly
    every filtered query."""
    store.clear_cache()
    before = store.vector_store.query_count
    store.search("agent", limit=1, category="Research")
    assert store.vector_store.query_count - before == 1


def test_an_unfiltered_search_asks_only_for_what_it_needs(store):
    store.clear_cache()
    store.search("agent", limit=1)
    assert store.vector_store.last_k == 1


def test_an_unreadable_index_size_does_not_blank_every_search(store):
    """_indexed_count() returns 0 when index.ntotal cannot be read. Clamping
    k to that would ask FAISS for nothing, and the empty result would be
    cached — turning a transient read failure into a dead search."""
    store.clear_cache()
    del store.vector_store.index.ntotal

    results = store.search("agent", limit=3)
    assert results, "a search returned nothing because the index size was unreadable"


def test_category_filter_is_case_insensitive(store):
    assert store.search("agent", category="code generation")
    assert store.search("agent", category="CODE GENERATION")


def test_unknown_category_returns_nothing(store):
    assert store.search("agent", category="Nonexistent") == []


def test_an_unknown_category_costs_no_embedding(store):
    """No indexed agent has it, so no amount of searching will find one.
    Embedding the query first would be ~91% of a search spent proving it."""
    store.clear_cache()
    before = store.vector_store.query_count

    assert store.search("agent", category="Nonexistent") == []
    assert store.vector_store.query_count == before, "it searched anyway"


def test_a_known_category_still_searches(store):
    """The early exit must not swallow a category that does have members."""
    store.clear_cache()
    before = store.vector_store.query_count

    assert store.search("agent", category="Code Generation")
    assert store.vector_store.query_count > before


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


class TestNameMatchRespectsFilters:
    """An injected name match must obey the filters search() applied.

    Searching "Cursor" inside category=Robotics returned Cursor at rank 0
    while metadata.category still claimed the filter held, and min_score
    could not suppress it.
    """

    def test_a_name_match_outside_the_category_is_not_injected(self, store):
        results = store.search("Cursor", limit=3, category="Research")
        assert "Cursor" not in [r["name"] for r in results]
        assert all(r["metadata"]["category"] == "Research" for r in results)

    def test_a_name_match_inside_the_category_is_still_hoisted(self, store):
        results = store.search("Cursor", limit=3, category="Code Generation")
        assert results[0]["name"] == "Cursor"
        assert results[0]["match"] == "name"

    def test_an_unfiltered_search_is_unaffected(self, store):
        assert store.search("Cursor", limit=1)[0]["match"] == "name"

    def test_the_category_filter_is_case_insensitive_here_too(self, store):
        assert store.search("Cursor", limit=3, category="code generation")[0]["name"] == "Cursor"


class TestRebuildingWithNoAgents:
    """Deleting every agent then reindexing is a legitimate state.

    add_agents early-returns on an empty list, so replace_agents used to null
    the store and stop — leaving the memoized agent list serving the deleted
    agents while stats reported zero, and the untouched index on disk
    resurrecting them all on the next restart.
    """

    def test_search_returns_nothing(self, store):
        store.replace_agents([])
        assert store.search("agent") == []

    def test_the_agent_list_is_not_stale(self, store):
        store.get_all_agents()          # warm the memo
        store.replace_agents([])
        assert store.get_all_agents() == []

    def test_stats_agree_with_the_listing(self, store):
        store.replace_agents([])
        assert store.get_stats()["count"] == 0
        assert store.get_categories() == []

    def test_the_sidecar_records_the_empty_index(self, store):
        """Otherwise a restart reloads the old index and resurrects them."""
        store.replace_agents([])
        assert store._read_meta().get("agent_count") == 0

    def test_lookup_by_name_finds_nothing(self, store):
        store.get_agent("Cursor")       # warm the name index
        store.replace_agents([])
        assert store.get_agent("Cursor") is None

    def test_a_direct_add_of_nothing_still_changes_nothing(self, store):
        """add_agents([]) is a no-op; only replace_agents([]) empties."""
        before = store.vector_store
        store.add_agents([])
        assert store.vector_store is before
        assert len(store.get_all_agents()) == 3


def test_an_unreadable_catalogue_does_not_empty_every_filtered_search(store, monkeypatch):
    """The fast path skips searching when no agent has the category. But
    get_categories() returns [] when the docstore *and* agents.json are both
    unreadable, and "I cannot tell" is not "the category is empty" — that
    would blank and cache every filtered search against a healthy index.
    """
    store.clear_cache()
    monkeypatch.setattr(store, "get_categories", lambda: [])

    assert store.search("agent", limit=3, category="Code Generation"), \
        "a filtered search went empty because the category list was unreadable"
