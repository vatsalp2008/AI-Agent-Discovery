import pytest

import api


def test_search_returns_scored_results(client):
    response = client.post("/api/search", json={"query": "code editor"})
    assert response.status_code == 200

    body = response.get_json()
    assert body["metadata"]["count"] == len(body["results"])
    assert [r["score"] for r in body["results"]] == sorted(
        (r["score"] for r in body["results"]), reverse=True
    )


def test_search_respects_limit(client):
    response = client.post("/api/search", json={"query": "agent", "limit": 2})
    assert response.status_code == 200
    body = response.get_json()
    assert len(body["results"]) <= 2
    assert body["metadata"]["limit"] == 2


def test_search_clamps_limit_to_the_configured_maximum(client):
    import config

    response = client.post("/api/search", json={"query": "agent", "limit": 10_000})
    assert response.get_json()["metadata"]["limit"] == config.SEARCH_MAX_LIMIT


def test_search_filters_by_category(client):
    response = client.post("/api/search", json={"query": "agent", "category": "Research"})
    assert response.status_code == 200
    results = response.get_json()["results"]
    assert results
    assert {r["metadata"]["category"] for r in results} == {"Research"}


@pytest.mark.parametrize(
    "payload,message",
    [
        ({}, "No query provided"),
        ({"query": ""}, "No query provided"),
        ({"query": "   "}, "No query provided"),
        ({"query": 42}, "'query' must be a string"),
        ({"query": "ok", "limit": "abc"}, "'limit' must be an integer"),
        ({"query": "ok", "limit": 0}, "'limit' must be at least 1"),
        ({"query": "ok", "category": 5}, "'category' must be a string"),
    ],
)
def test_search_rejects_bad_payloads(client, payload, message):
    response = client.post("/api/search", json=payload)
    assert response.status_code == 400
    assert response.get_json()["error"] == message


def test_search_rejects_an_overlong_query(client):
    import config

    response = client.post("/api/search", json={"query": "x" * (config.MAX_QUERY_LENGTH + 1)})
    assert response.status_code == 400


def test_search_rejects_a_non_json_body(client):
    """Previously raised a 415 from request.json before the handler ran."""
    response = client.post("/api/search", data="not json", content_type="text/plain")
    assert response.status_code == 400
    assert "JSON object" in response.get_json()["error"]


def test_agents_endpoint_lists_every_indexed_agent(client):
    response = client.get("/api/agents")
    assert response.status_code == 200
    body = response.get_json()
    names = [a["name"] for a in body["agents"]]
    assert names == sorted(names, key=str.lower)
    assert "Cursor" in names
    assert body["metadata"]["total"] == 3
    assert body["metadata"]["has_more"] is False


def test_agents_endpoint_paginates(client):
    first = client.get("/api/agents?limit=2").get_json()
    assert [a["name"] for a in first["agents"]] == ["Aider", "Cursor"]
    assert first["metadata"] == {
        "total": 3, "count": 2, "limit": 2, "offset": 0,
        "category": None, "sort": "name", "order": "asc", "has_more": True,
    }

    second = client.get("/api/agents?limit=2&offset=2").get_json()
    assert [a["name"] for a in second["agents"]] == ["GPT Researcher"]
    assert second["metadata"]["has_more"] is False


def test_agents_offset_past_the_end_returns_an_empty_page(client):
    body = client.get("/api/agents?offset=99").get_json()
    assert body["agents"] == []
    assert body["metadata"]["total"] == 3
    assert body["metadata"]["has_more"] is False


def test_agents_page_size_is_capped(client):
    import config

    body = client.get("/api/agents?limit=99999").get_json()
    assert body["metadata"]["limit"] == config.AGENTS_MAX_PAGE_SIZE


@pytest.mark.parametrize("query", ["limit=abc", "limit=0", "offset=-1", "offset=xyz"])
def test_agents_rejects_bad_pagination_args(client, query):
    response = client.get(f"/api/agents?{query}")
    assert response.status_code == 400
    assert response.is_json


def test_categories_endpoint_counts_agents(client):
    response = client.get("/api/categories")
    assert response.status_code == 200
    categories = response.get_json()
    assert categories[0] == {"name": "Code Generation", "count": 2}
    assert {"name": "Research", "count": 1} in categories


def test_stats_endpoint_reports_index_size(client):
    assert client.get("/api/stats").get_json()["count"] == 3


def test_health_is_ok_when_the_index_is_populated(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.get_json()["status"] == "ok"


def test_health_is_degraded_when_nothing_is_indexed(client):
    class Empty:
        def get_stats(self):
            return {"count": 0}

    api.set_store(Empty())
    response = client.get("/api/health")
    assert response.status_code == 503
    assert response.get_json()["status"] == "degraded"


def test_health_reports_an_unreachable_backend(client):
    class Broken:
        def get_stats(self):
            raise RuntimeError("ollama unreachable")

    api.set_store(Broken())
    response = client.get("/api/health")
    assert response.status_code == 503
    assert response.get_json()["status"] == "error"


def test_stats_summarizes_the_catalogue(client):
    """The dashboard reads these instead of downloading every agent."""
    stats = client.get("/api/stats").get_json()
    assert stats["count"] == 3
    assert stats["categories"] == 2
    assert stats["top_category"] == {"name": "Code Generation", "count": 2}
    assert stats["total_stars"] == 35000 + 12000 + 14000
    assert stats["average_stars"] == round(61000 / 3)
    assert stats["embedding_model"]


def test_stats_on_an_empty_index_does_not_divide_by_zero(client, tmp_path):
    from vectorstore import VectorStore

    api.set_store(VectorStore(persist_directory=tmp_path / "empty", embedding_function=object()))
    stats = client.get("/api/stats").get_json()
    assert stats["count"] == 0
    assert stats["average_stars"] == 0
    assert stats["top_category"] is None


def test_agent_detail_returns_a_single_agent(client):
    body = client.get("/api/agents/Cursor").get_json()
    assert body["name"] == "Cursor"
    assert body["metadata"]["category"] == "Code Generation"


def test_agent_detail_is_case_insensitive(client):
    assert client.get("/api/agents/cursor").get_json()["name"] == "Cursor"
    assert client.get("/api/agents/CURSOR").get_json()["name"] == "Cursor"


def test_agent_detail_handles_names_with_spaces(client):
    assert client.get("/api/agents/GPT Researcher").status_code == 200


def test_unknown_agent_returns_404_json(client):
    response = client.get("/api/agents/Nonexistent")
    assert response.status_code == 404
    assert response.is_json
    assert "Nonexistent" in response.get_json()["error"]


def test_agent_detail_does_not_shadow_the_list_endpoint(client):
    assert "agents" in client.get("/api/agents").get_json()


def test_search_omits_a_summary_by_default(client):
    body = client.post("/api/search", json={"query": "code editor"}).get_json()
    assert body["summary"] is None
    assert body["metadata"]["summarized"] is False


def test_search_includes_a_summary_when_requested(client, monkeypatch):
    import generation

    monkeypatch.setattr(generation, "summarize", lambda q, r: "Cursor fits best.")
    body = client.post("/api/search", json={"query": "code editor", "summarize": True}).get_json()
    assert body["summary"] == "Cursor fits best."
    assert body["metadata"]["summarized"] is True


def test_results_survive_a_failing_summary(client, monkeypatch):
    """Generation is best-effort: losing it must not lose the search."""
    import generation

    def broken(query, results):
        raise RuntimeError("ollama is down")

    monkeypatch.setattr(generation, "summarize", broken)
    response = client.post("/api/search", json={"query": "code editor", "summarize": True})
    assert response.status_code == 500  # surfaced, not silently swallowed


def test_unavailable_summary_still_returns_results(client, monkeypatch):
    import generation

    monkeypatch.setattr(generation, "summarize", lambda q, r: None)
    body = client.post("/api/search", json={"query": "code editor", "summarize": True}).get_json()
    assert len(body["results"]) > 0
    assert body["summary"] is None
    assert body["metadata"]["summarized"] is False


@pytest.mark.parametrize("value", ["yes", 1, "true", []])
def test_search_rejects_a_non_boolean_summarize(client, value):
    response = client.post("/api/search", json={"query": "ok", "summarize": value})
    assert response.status_code == 400
    assert response.get_json()["error"] == "'summarize' must be a boolean"


def test_search_reports_confidence(client):
    body = client.post("/api/search", json={"query": "code editor"}).get_json()
    assert body["metadata"]["confident"] is True


def test_weak_matches_are_flagged_not_hidden(client, weak_store):
    """A nonsense query still returns results, but must not claim they are good."""
    body = client.post("/api/search", json={"query": "banana bread"}).get_json()
    assert body["metadata"]["confident"] is False
    assert len(body["results"]) > 0
    assert body["results"][0]["score"] < 0.5


def test_no_overview_is_generated_for_weak_matches(client, weak_store, monkeypatch):
    """An overview of irrelevant tools reads as confident nonsense."""
    import generation

    called = []
    monkeypatch.setattr(generation, "summarize", lambda q, r: called.append(1) or "text")

    body = client.post("/api/search", json={"query": "banana", "summarize": True}).get_json()
    assert called == []
    assert body["summary"] is None


def test_min_score_hard_filters(client):
    """Unlike the confidence flag, min_score removes results outright."""
    unfiltered = client.post("/api/search", json={"query": "agent"}).get_json()
    assert len(unfiltered["results"]) == 3

    body = client.post("/api/search", json={"query": "agent", "min_score": 0.99}).get_json()
    assert [r["name"] for r in body["results"]] == ["Cursor"]  # only the distance-0 hit
    assert body["metadata"]["min_score"] == 0.99


def test_min_score_can_filter_everything_out(client, weak_store):
    body = client.post("/api/search", json={"query": "banana", "min_score": 0.9}).get_json()
    assert body["results"] == []
    assert body["metadata"]["confident"] is False


@pytest.mark.parametrize("value", ["0.5", True, [], 1.5, -0.1])
def test_search_rejects_a_bad_min_score(client, value):
    response = client.post("/api/search", json={"query": "ok", "min_score": value})
    assert response.status_code == 400


def test_agents_can_be_filtered_by_category(client):
    body = client.get("/api/agents?category=Code Generation").get_json()
    assert [a["name"] for a in body["agents"]] == ["Aider", "Cursor"]
    assert body["metadata"]["total"] == 2
    assert body["metadata"]["category"] == "Code Generation"


def test_agents_category_filter_is_case_insensitive(client):
    assert client.get("/api/agents?category=code generation").get_json()["metadata"]["total"] == 2


def test_agents_category_filter_combines_with_paging(client):
    body = client.get("/api/agents?category=Code Generation&limit=1").get_json()
    assert body["metadata"]["count"] == 1
    assert body["metadata"]["total"] == 2
    assert body["metadata"]["has_more"] is True


def test_agents_unknown_category_is_empty_not_an_error(client):
    body = client.get("/api/agents?category=Nonexistent").get_json()
    assert body["agents"] == []
    assert body["metadata"]["total"] == 0


def test_agents_blank_category_is_ignored(client):
    assert client.get("/api/agents?category=%20").get_json()["metadata"]["total"] == 3


def test_agents_sort_by_stars_defaults_to_descending(client):
    body = client.get("/api/agents?sort=stars").get_json()
    stars = [a["metadata"]["stars"] for a in body["agents"]]
    assert stars == sorted(stars, reverse=True)
    assert body["metadata"]["order"] == "desc"


def test_agents_sort_by_name_defaults_to_ascending(client):
    body = client.get("/api/agents?sort=name").get_json()
    assert [a["name"] for a in body["agents"]] == ["Aider", "Cursor", "GPT Researcher"]
    assert body["metadata"]["order"] == "asc"


def test_agents_sort_direction_can_be_reversed(client):
    body = client.get("/api/agents?sort=name&order=desc").get_json()
    assert [a["name"] for a in body["agents"]] == ["GPT Researcher", "Cursor", "Aider"]


def test_agents_sort_by_category_breaks_ties_by_name(client):
    names = [a["name"] for a in client.get("/api/agents?sort=category").get_json()["agents"]]
    assert names == ["Aider", "Cursor", "GPT Researcher"]


def test_agents_default_sort_is_by_name(client):
    body = client.get("/api/agents").get_json()
    assert body["metadata"]["sort"] == "name"


@pytest.mark.parametrize("query", ["sort=bogus", "sort=name&order=sideways"])
def test_agents_rejects_a_bad_sort(client, query):
    response = client.get(f"/api/agents?{query}")
    assert response.status_code == 400
    assert response.is_json


def test_agents_sort_does_not_corrupt_the_cached_list(client, store):
    """The handler sorts in place; it must be working on a copy."""
    client.get("/api/agents?sort=stars&order=desc")
    assert [a["name"] for a in store.get_all_agents()] == ["Aider", "Cursor", "GPT Researcher"]
