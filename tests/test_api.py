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
        "total": 3, "count": 2, "limit": 2, "offset": 0, "has_more": True
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
