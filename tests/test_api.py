import json

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
        "category": None, "tech": None, "q": None,
        "min_stars": None, "max_stars": None,
        "sort": "name", "order": "asc", "has_more": True,
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


def test_tech_endpoint_lists_technologies_with_counts(client):
    body = client.get("/api/tech").get_json()
    names = [t["name"] for t in body]
    assert "Python" in names
    # Most common first.
    counts = [t["count"] for t in body]
    assert counts == sorted(counts, reverse=True)


def test_tech_endpoint_splits_the_comma_joined_stack(client):
    """stack is stored as one string because FAISS metadata must be scalar."""
    names = [t["name"] for t in client.get("/api/tech").get_json()]
    assert "Electron" in names and "GPT-4" in names
    assert not any("," in n for n in names)


def test_agents_can_be_filtered_by_tech(client):
    body = client.get("/api/agents?tech=Python").get_json()
    assert body["metadata"]["tech"] == "Python"
    for agent in body["agents"]:
        assert "Python" in agent["metadata"]["stack"]


def test_tech_filter_is_case_insensitive(client):
    lower = client.get("/api/agents?tech=python").get_json()["metadata"]["total"]
    upper = client.get("/api/agents?tech=PYTHON").get_json()["metadata"]["total"]
    assert lower == upper > 0


def test_tech_filter_matches_whole_entries_not_substrings(client):
    """'GPT' must not match the 'GPT-4' entry."""
    assert client.get("/api/agents?tech=GPT").get_json()["metadata"]["total"] == 0
    assert client.get("/api/agents?tech=GPT-4").get_json()["metadata"]["total"] > 0


def test_tech_and_category_filters_combine(client):
    body = client.get("/api/agents?tech=Python&category=Code Generation").get_json()
    for agent in body["agents"]:
        assert agent["metadata"]["category"] == "Code Generation"
        assert "Python" in agent["metadata"]["stack"]


def test_agents_keyword_filter_matches_names(client):
    body = client.get("/api/agents?q=curs").get_json()
    assert [a["name"] for a in body["agents"]] == ["Cursor"]
    assert body["metadata"]["q"] == "curs"


def test_agents_keyword_filter_matches_descriptions(client):
    body = client.get("/api/agents?q=editor").get_json()
    assert "Cursor" in [a["name"] for a in body["agents"]]


def test_agents_keyword_filter_is_case_insensitive(client):
    assert client.get("/api/agents?q=CURSOR").get_json()["metadata"]["total"] == 1


def test_agents_keyword_filter_combines_with_category(client):
    body = client.get("/api/agents?q=e&category=Research").get_json()
    for agent in body["agents"]:
        assert agent["metadata"]["category"] == "Research"


def test_agents_keyword_no_match_is_empty(client):
    assert client.get("/api/agents?q=zzzznope").get_json()["metadata"]["total"] == 0


def test_agents_blank_keyword_is_ignored(client):
    assert client.get("/api/agents?q=%20").get_json()["metadata"]["total"] == 3


def test_similar_endpoint_is_not_swallowed_by_the_detail_route(client):
    """/agents/<path:name> matches slashes, so ordering matters here."""
    body = client.get("/api/agents/Cursor/similar").get_json()
    assert "agents" in body
    assert body["metadata"]["of"] == "Cursor"


def test_similar_excludes_the_agent_itself(client):
    body = client.get("/api/agents/Cursor/similar").get_json()
    assert "Cursor" not in [a["name"] for a in body["agents"]]


def test_similar_returns_the_requested_count(client):
    """Over-fetching means asking for N does not yield N-1."""
    body = client.get("/api/agents/Cursor/similar?limit=2").get_json()
    assert body["metadata"]["count"] == 2
    assert len(body["agents"]) == 2


def test_similar_defaults_to_three(client):
    assert client.get("/api/agents/Cursor/similar").get_json()["metadata"]["limit"] == 3


def test_similar_for_an_unknown_agent_is_404(client):
    response = client.get("/api/agents/Nope/similar")
    assert response.status_code == 404
    assert response.is_json


def test_similar_is_case_insensitive(client):
    assert client.get("/api/agents/cursor/similar").status_code == 200


def test_similar_rejects_a_bad_limit(client):
    assert client.get("/api/agents/Cursor/similar?limit=0").status_code == 400


def test_compare_returns_several_agents(client):
    body = client.get("/api/compare?names=Cursor,Aider").get_json()
    assert [a["name"] for a in body["agents"]] == ["Cursor", "Aider"]
    assert body["metadata"] == {"requested": 2, "count": 2, "missing": []}


def test_compare_preserves_the_requested_order(client):
    body = client.get("/api/compare?names=Aider,Cursor").get_json()
    assert [a["name"] for a in body["agents"]] == ["Aider", "Cursor"]


def test_compare_reports_unknown_names_without_discarding_the_rest(client):
    """One typo should not throw away the agents that did resolve."""
    body = client.get("/api/compare?names=Cursor,Nope").get_json()
    assert [a["name"] for a in body["agents"]] == ["Cursor"]
    assert body["metadata"]["missing"] == ["Nope"]
    assert body["metadata"]["requested"] == 2


def test_compare_is_case_insensitive(client):
    assert client.get("/api/compare?names=cursor").get_json()["metadata"]["count"] == 1


def test_compare_ignores_blank_entries(client):
    body = client.get("/api/compare?names=Cursor,,%20,Aider").get_json()
    assert body["metadata"]["requested"] == 2


def test_compare_requires_at_least_one_name(client):
    for query in ["", "names=", "names=%20"]:
        response = client.get(f"/api/compare?{query}")
        assert response.status_code == 400, query


def test_compare_caps_the_number_of_agents(client):
    import config

    names = ",".join(f"a{i}" for i in range(config.COMPARE_MAX_AGENTS + 1))
    response = client.get(f"/api/compare?names={names}")
    assert response.status_code == 400
    assert "at most" in response.get_json()["error"]


@pytest.mark.parametrize("path", ["/api/categories", "/api/tech", "/api/stats"])
def test_catalogue_endpoints_send_an_etag(client, path):
    response = client.get(path)
    assert response.status_code == 200
    assert response.headers.get("ETag")
    assert response.headers["Cache-Control"] == "no-cache"


@pytest.mark.parametrize("path", ["/api/categories", "/api/tech", "/api/stats"])
def test_matching_etag_returns_304_with_no_body(client, path):
    etag = client.get(path).headers["ETag"]
    response = client.get(path, headers={"If-None-Match": etag})
    assert response.status_code == 304
    assert response.get_data() == b""


def test_stale_etag_returns_the_body(client):
    response = client.get("/api/categories", headers={"If-None-Match": '"stale"'})
    assert response.status_code == 200
    assert response.get_json()


def test_etag_changes_when_the_data_changes(client, store, agents):
    before = client.get("/api/stats").headers["ETag"]
    store.add_agents(agents)          # index changed
    after = client.get("/api/stats").headers["ETag"]
    assert before != after


def test_etag_is_stable_for_unchanged_data(client):
    assert client.get("/api/tech").headers["ETag"] == client.get("/api/tech").headers["ETag"]


class TestOpenApi:
    """Generated from the live URL map, so it cannot drift from the routes."""

    def test_describes_itself_as_openapi(self, client):
        spec = client.get("/api/openapi.json").get_json()
        assert spec["openapi"].startswith("3.")
        assert spec["info"]["title"]

    def test_every_api_route_appears(self, client):
        spec = client.get("/api/openapi.json").get_json()
        for path in ["/api/search", "/api/agents", "/api/categories",
                     "/api/tech", "/api/stats", "/api/health", "/api/compare"]:
            assert path in spec["paths"], f"{path} missing from the spec"

    def test_no_non_api_route_leaks_in(self, client):
        spec = client.get("/api/openapi.json").get_json()
        assert all(p.startswith("/api/") for p in spec["paths"])

    def test_path_parameters_use_openapi_syntax(self, client):
        """Flask writes <path:name>; OpenAPI wants {name}."""
        spec = client.get("/api/openapi.json").get_json()
        assert "/api/agents/{name}" in spec["paths"]
        assert not any("<" in p for p in spec["paths"])

    def test_path_parameters_are_declared(self, client):
        spec = client.get("/api/openapi.json").get_json()
        params = spec["paths"]["/api/agents/{name}"]["get"]["parameters"]
        assert [p["name"] for p in params] == ["name"]

    def test_methods_match_the_routes(self, client):
        spec = client.get("/api/openapi.json").get_json()
        assert set(spec["paths"]["/api/search"]) == {"post"}
        assert set(spec["paths"]["/api/agents"]) == {"get"}

    def test_summaries_come_from_docstrings(self, client):
        spec = client.get("/api/openapi.json").get_json()
        assert "similar" in spec["paths"]["/api/agents/{name}/similar"]["get"]["summary"].lower()

    def test_the_spec_itself_is_listed(self, client):
        spec = client.get("/api/openapi.json").get_json()
        assert "/api/openapi.json" in spec["paths"]


class TestStarsFilter:
    def test_min_stars_excludes_smaller_projects(self, client):
        """Cursor 35000, GPT Researcher 14000, Aider 12000."""
        body = client.get("/api/agents?min_stars=13000").get_json()
        assert sorted(a["name"] for a in body["agents"]) == ["Cursor", "GPT Researcher"]
        assert body["metadata"]["min_stars"] == 13000

    def test_max_stars_excludes_larger_projects(self, client):
        body = client.get("/api/agents?max_stars=13000").get_json()
        assert [a["name"] for a in body["agents"]] == ["Aider"]

    def test_a_range_selects_between(self, client):
        body = client.get("/api/agents?min_stars=13000&max_stars=20000").get_json()
        assert [a["name"] for a in body["agents"]] == ["GPT Researcher"]

    def test_bounds_are_inclusive(self, client):
        assert client.get("/api/agents?min_stars=35000").get_json()["metadata"]["total"] == 1
        assert client.get("/api/agents?max_stars=12000").get_json()["metadata"]["total"] == 1

    def test_an_inverted_range_is_rejected(self, client):
        response = client.get("/api/agents?min_stars=100&max_stars=10")
        assert response.status_code == 400
        assert "cannot exceed" in response.get_json()["error"]

    def test_negative_bounds_are_rejected(self, client):
        assert client.get("/api/agents?min_stars=-1").status_code == 400

    def test_combines_with_the_other_filters(self, client):
        body = client.get("/api/agents?min_stars=1&category=Code Generation").get_json()
        for agent in body["agents"]:
            assert agent["metadata"]["category"] == "Code Generation"

    def test_absent_by_default(self, client):
        metadata = client.get("/api/agents").get_json()["metadata"]
        assert metadata["min_stars"] is None
        assert metadata["max_stars"] is None


class TestOpenApiSchemas:
    def test_the_search_response_is_described(self, client):
        spec = client.get("/api/openapi.json").get_json()
        assert "SearchResponse" in spec["components"]["schemas"]
        ref = spec["paths"]["/api/search"]["post"]["responses"]["200"]
        assert "SearchResponse" in json.dumps(ref)

    def test_the_match_field_is_documented(self, client):
        """A caller has to know 1.0 can mean 'name match', not 'perfect similarity'."""
        result = client.get("/api/openapi.json").get_json()["components"]["schemas"]["SearchResult"]
        assert result["properties"]["match"]["enum"] == ["semantic", "name"]
        assert "not a similarity" in result["properties"]["score"]["description"]

    def test_confidence_is_documented(self, client):
        spec = client.get("/api/openapi.json").get_json()
        meta = spec["components"]["schemas"]["SearchResponse"]["properties"]["metadata"]
        assert "SEARCH_MIN_SCORE" in meta["properties"]["confident"]["description"]

    def test_every_schema_reference_resolves(self, client):
        """A dangling $ref makes the spec unusable in a generator."""
        import re

        spec = client.get("/api/openapi.json").get_json()
        defined = set(spec["components"]["schemas"])
        referenced = set(re.findall(r"#/components/schemas/(\w+)", json.dumps(spec)))
        assert referenced <= defined, f"dangling refs: {referenced - defined}"


class TestNameMatchAndConfidence:
    """A name match scores 1.0, which necessarily makes the response confident.

    That is the intent — searching an agent's exact name is not a guess — but
    it interacts with two other behaviours, so pin it rather than leave it to
    be rediscovered.
    """

    def test_a_name_match_is_treated_as_confident(self, client):
        body = client.post("/api/search", json={"query": "Cursor"}).get_json()
        assert body["results"][0]["match"] == "name"
        assert body["metadata"]["confident"] is True

    def test_no_weak_match_notice_for_a_name_match(self, weak_store, client):
        """Even when every semantic score is poor, naming an agent is not a
        failed search, so it must not be reported as one."""
        body = client.post("/api/search", json={"query": "Cursor"}).get_json()
        assert body["results"][0]["name"] == "Cursor"
        assert body["metadata"]["confident"] is True

    def test_min_score_does_not_filter_out_a_name_match(self, weak_store, client):
        """It scores 1.0, so any threshold keeps it."""
        body = client.post("/api/search", json={"query": "Cursor", "min_score": 0.9}).get_json()
        assert [r["name"] for r in body["results"]] == ["Cursor"]

    def test_a_nonsense_query_is_still_flagged(self, weak_store, client):
        body = client.post("/api/search", json={"query": "banana bread"}).get_json()
        assert body["metadata"]["confident"] is False


def test_the_client_compare_cap_matches_the_server(client):
    """collections.js builds /compare links from its own constant. If it
    drifts above COMPARE_MAX_AGENTS the link is refused on arrival, which
    reads as a broken collection rather than a limit."""
    import re

    import config

    static_js = config.PACKAGE_DIR / "frontend" / "static" / "js"
    for name in ("collections.js", "compare.js"):
        source = (static_js / name).read_text()
        declared = re.search(r"const DEFAULT_MAX_COMPARE = (\d+);", source)

        assert declared, f"{name} no longer declares DEFAULT_MAX_COMPARE"
        assert int(declared.group(1)) <= config.COMPARE_MAX_AGENTS, name
