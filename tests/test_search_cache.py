"""Repeat searches should not re-embed the query."""

import config


def _query_count(store):
    return store.vector_store.query_count


def test_repeat_search_hits_the_cache(store):
    store.search("code editor")
    assert _query_count(store) == 1

    store.search("code editor")
    assert _query_count(store) == 1


def test_cache_is_case_insensitive(store):
    store.search("Code Editor")
    store.search("code editor")
    assert _query_count(store) == 1


def test_different_limits_are_cached_separately(store):
    store.search("agent", limit=1)
    store.search("agent", limit=2)
    assert _query_count(store) == 2


def test_different_categories_are_cached_separately(store):
    store.search("agent", category="Research")
    store.search("agent", category="Code Generation")
    assert _query_count(store) == 2


def test_cached_results_match_fresh_results(store):
    first = store.search("agent", limit=2)
    second = store.search("agent", limit=2)
    assert first == second


def test_mutating_a_result_does_not_poison_the_cache(store):
    first = store.search("agent", limit=2)
    first[0]["name"] = "MUTATED"
    assert store.search("agent", limit=2)[0]["name"] != "MUTATED"


def test_reindexing_invalidates_the_cache(store, agents):
    store.search("agent")
    assert _query_count(store) == 1

    store.add_agents(agents)
    store.search("agent")
    assert _query_count(store) == 2


def test_cache_is_bounded(store, monkeypatch):
    monkeypatch.setattr(config, "SEARCH_CACHE_SIZE", 3)
    for i in range(10):
        store.search(f"query {i}")
    assert len(store._search_cache) == 3


def test_cache_evicts_least_recently_used(store, monkeypatch):
    monkeypatch.setattr(config, "SEARCH_CACHE_SIZE", 2)
    store.search("first")
    store.search("second")
    store.search("first")   # refreshes "first"
    store.search("third")   # should evict "second"

    before = _query_count(store)
    store.search("first")
    assert _query_count(store) == before  # still cached

    store.search("second")
    assert _query_count(store) == before + 1  # was evicted


def test_caching_can_be_disabled(store, monkeypatch):
    monkeypatch.setattr(config, "SEARCH_CACHE_SIZE", 0)
    store.search("agent")
    store.search("agent")
    assert _query_count(store) == 2
