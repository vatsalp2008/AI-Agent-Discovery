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
        "category": None, "tech": None, "maintained": False, "q": None,
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


@pytest.fixture
def history(tmp_path, monkeypatch):
    """Points DATA_DIR at a throwaway directory; call it to write a file.

    Shared by the JSON endpoint and the Atom feed, which read the same file.
    """
    import config

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)

    def write(contents):
        import json as _json

        path = tmp_path / "changelog.json"
        path.write_text(contents if isinstance(contents, str) else _json.dumps(contents))
        return path

    return write


class TestChangelog:
    """Served from a generated file, so the interesting cases are what
    happens when it is absent or damaged."""

    def test_it_returns_the_history(self, client, history):
        history([{"commit": "abc", "at": "2026-08-14T00:00:00+00:00",
                  "subject": "Add agents", "total": 223,
                  "added": ["Kedro"], "removed": [], "edited": []}])

        body = client.get("/api/changelog").get_json()
        assert body["entries"][0]["added"] == ["Kedro"]
        assert body["metadata"]["total"] == 1

    def test_an_absent_file_is_an_empty_history(self, client, history):
        """The normal state before the generator has ever run, and a truthful
        answer to "what changed" — not a 500."""
        response = client.get("/api/changelog")
        assert response.status_code == 200
        assert response.get_json()["entries"] == []

    def test_a_damaged_file_is_not_a_crash(self, client, history):
        history("{ not json")

        assert client.get("/api/changelog").get_json()["entries"] == []

    def test_a_file_that_is_not_a_list_is_not_served(self, client, history):
        history('{"entries": []}')

        assert client.get("/api/changelog").get_json()["entries"] == []

    def test_the_limit_is_honoured(self, client, history):
        history([{"commit": str(i), "at": "", "subject": "", "total": 1,
                  "added": [], "removed": [], "edited": []} for i in range(10)])

        body = client.get("/api/changelog?limit=3").get_json()
        assert len(body["entries"]) == 3
        assert body["metadata"]["total"] == 10, "total should be the whole history"

    def test_a_bad_limit_is_refused(self, client):
        assert client.get("/api/changelog?limit=nonsense").status_code == 400

    def test_it_carries_an_etag(self, client, history):
        response = client.get("/api/changelog")
        etag = response.headers.get("ETag")

        assert etag
        assert client.get("/api/changelog",
                          headers={"If-None-Match": etag}).status_code == 304


class TestMaintainedFilter:
    """19 of 223 entries are archived or dormant. A directory that ranks an
    abandoned tool beside a live one is answering the wrong question."""

    def test_search_keeps_everything_by_default(self, client):
        body = client.post("/api/search", json={"query": "agent"}).get_json()
        assert body["metadata"]["maintained"] is False

    def test_search_can_hide_abandoned_projects(self, client, store):
        body = client.post("/api/search",
                           json={"query": "agent", "maintained": True}).get_json()

        assert body["metadata"]["maintained"] is True
        statuses = {r["metadata"].get("status", "active") for r in body["results"]}
        assert statuses <= {"active"}

    def test_a_non_boolean_is_refused(self, client):
        response = client.post("/api/search", json={"query": "x", "maintained": "yes"})
        assert response.status_code == 400
        assert "maintained" in response.get_json()["error"]

    def test_the_listing_filters_too(self, client):
        body = client.get("/api/agents?maintained=1").get_json()
        assert body["metadata"]["maintained"] is True
        assert all((a["metadata"].get("status") or "active") == "active"
                   for a in body["agents"])

    @pytest.mark.parametrize("value", ["1", "true", "yes", "on", "TRUE"])
    def test_the_listing_accepts_the_usual_spellings(self, client, value):
        """A query string has no booleans, so the usual ones all work."""
        body = client.get(f"/api/agents?maintained={value}").get_json()
        assert body["metadata"]["maintained"] is True

    @pytest.mark.parametrize("value", ["0", "false", "no", "", "maybe"])
    def test_anything_else_leaves_the_listing_unfiltered(self, client, value):
        body = client.get(f"/api/agents?maintained={value}").get_json()
        assert body["metadata"]["maintained"] is False


class TestChangelogFeed:
    """Atom rather than RSS: it requires a stable id and a real timestamp per
    entry, and a git commit already has both."""

    NS = "{http://www.w3.org/2005/Atom}"

    def parse(self, client):
        import xml.etree.ElementTree as ET

        response = client.get("/api/changelog.atom")
        assert response.status_code == 200
        assert "atom+xml" in response.headers["Content-Type"]
        return ET.fromstring(response.get_data())

    def test_it_is_well_formed_atom(self, client, history):
        history([{"commit": "abc12345", "at": "2026-08-14T00:00:00+00:00",
                  "subject": "Add agents", "total": 223,
                  "added": ["Kedro"], "removed": [], "edited": []}])
        feed = self.parse(client)

        assert feed.find(f"{self.NS}title") is not None
        assert feed.find(f"{self.NS}id") is not None
        assert len(feed.findall(f"{self.NS}entry")) == 1

    def test_an_empty_history_is_still_a_valid_feed(self, client, history):
        """Readers treat a missing `updated` as malformed rather than as
        "nothing yet"."""
        feed = self.parse(client)

        assert feed.findall(f"{self.NS}entry") == []
        assert feed.find(f"{self.NS}updated").text

    def test_each_entry_is_identified_by_its_commit(self, client, history):
        """An id that shifts as history grows makes every reader re-announce
        every entry."""
        history([{"commit": "abc12345", "at": "2026-08-14T00:00:00+00:00",
                  "subject": "One", "total": 1, "added": [], "removed": [], "edited": []}])
        entry = self.parse(client).find(f"{self.NS}entry")

        assert "abc12345" in entry.find(f"{self.NS}id").text

    def test_the_summary_says_what_changed(self, client, history):
        history([{"commit": "abc", "at": "2026-08-14T00:00:00+00:00", "subject": "s",
                  "total": 223, "added": ["Kedro", "Gradio"], "removed": ["Gone"],
                  "edited": [{"name": "Cursor", "fields": []}]}])
        summary = self.parse(client).find(f"{self.NS}entry/{self.NS}summary").text

        assert "Added Kedro, Gradio" in summary
        assert "Removed Gone" in summary
        assert "Edited Cursor" in summary
        assert "223 agents" in summary

    def test_a_long_edit_list_is_abbreviated(self, client, history):
        """A feed reader shows a line, not a page."""
        history([{"commit": "abc", "at": "2026-08-14T00:00:00+00:00", "subject": "s",
                  "total": 1, "added": [], "removed": [],
                  "edited": [{"name": f"A{i}", "fields": []} for i in range(9)]}])
        summary = self.parse(client).find(f"{self.NS}entry/{self.NS}summary").text

        assert "and 4 more" in summary

    def test_it_is_capped(self, client, history):
        history([{"commit": str(i), "at": "2026-08-14T00:00:00+00:00", "subject": "s",
                  "total": 1, "added": [], "removed": [], "edited": []}
                 for i in range(80)])

        assert len(self.parse(client).findall(f"{self.NS}entry")) == 50

    def test_a_damaged_history_does_not_break_the_feed(self, client, history):
        history("{ not json")
        assert self.parse(client).findall(f"{self.NS}entry") == []


class TestFeedRobustness:
    NS = "{http://www.w3.org/2005/Atom}"

    def test_it_names_an_author(self, client, history):
        """RFC 4287 §4.1.2 requires one; validators flag every entry without
        it. On the feed, so entries inherit rather than repeat it."""
        import xml.etree.ElementTree as ET

        history([{"commit": "a", "at": "2026-08-14T00:00:00+00:00", "subject": "s",
                  "total": 1, "added": [], "removed": [], "edited": []}])
        feed = ET.fromstring(client.get("/api/changelog.atom").get_data())

        assert feed.find(f"{self.NS}author/{self.NS}name").text

    def test_junk_inside_the_history_does_not_500(self, client, history):
        """A list that parses can still hold anything. The JSON endpoint
        survives because it only slices; the feed reads fields."""
        history(["not an object", 7, None,
                 {"commit": "a", "at": "", "subject": "ok", "total": 1,
                  "added": [], "removed": [], "edited": []}])

        assert client.get("/api/changelog.atom").status_code == 200
        assert client.get("/api/changelog").status_code == 200

    def test_junk_is_left_out_of_both(self, client, history):
        history(["not an object", {"commit": "a", "at": "", "subject": "ok", "total": 1,
                                   "added": [], "removed": [], "edited": []}])

        body = client.get("/api/changelog").get_json()
        assert [e["subject"] for e in body["entries"]] == ["ok"]


def test_the_feed_satisfies_the_required_atom_elements(client, history):
    """RFC 4287 §4.1.1: a feed needs id, title and updated, and each entry
    needs the same three. Well-formed XML is not the same as valid Atom, and
    a reader that rejects the feed says nothing about why.
    """
    import xml.etree.ElementTree as ET

    ns = "{http://www.w3.org/2005/Atom}"
    history([{"commit": "abc12345", "at": "2026-08-16T00:00:00+00:00",
              "subject": "Add agents", "total": 236,
              "added": ["Kedro"], "removed": [], "edited": []}])
    feed = ET.fromstring(client.get("/api/changelog.atom").get_data())

    for element in ("id", "title", "updated", "author"):
        assert feed.find(f"{ns}{element}") is not None, f"the feed has no <{element}>"

    for entry in feed.findall(f"{ns}entry"):
        for element in ("id", "title", "updated"):
            found = entry.find(f"{ns}{element}")
            assert found is not None and found.text, f"an entry has no <{element}>"


def test_every_feed_entry_has_a_distinct_id(client, history):
    """Readers key on the id; a duplicate makes entries overwrite each other."""
    import xml.etree.ElementTree as ET

    ns = "{http://www.w3.org/2005/Atom}"
    history([{"commit": f"commit{i}", "at": "2026-08-16T00:00:00+00:00",
              "subject": f"Change {i}", "total": 1,
              "added": [], "removed": [], "edited": []} for i in range(5)])
    feed = ET.fromstring(client.get("/api/changelog.atom").get_data())

    ids = [e.find(f"{ns}id").text for e in feed.findall(f"{ns}entry")]
    assert len(set(ids)) == len(ids)


class TestFeedSurvivesADamagedHistory:
    """changelog.json is generated, but it is a file on disk that a person
    can edit and an older version may have written differently. The JSON
    endpoint survives anything because it only slices; the feed reads inside
    each entry, and was returning 500 where the JSON endpoint returned 200.
    """

    NS = "{http://www.w3.org/2005/Atom}"

    def entry(self, **overrides):
        base = {"commit": "abc12345", "at": "2026-08-16T00:00:00+00:00",
                "subject": "s", "total": 1, "added": [], "removed": [], "edited": []}
        base.update(overrides)
        return base

    @pytest.mark.parametrize("damage", [
        {"edited": ["Cursor"]},           # strings where objects belong
        {"edited": [None, 7]},
        {"added": [None]},                # nulls in a name list
        {"added": "Kedro"},               # a string where a list belongs
        {"removed": {"a": 1}},
        {"total": "lots"},
        {"at": None},
        {"at": ""},
        {"subject": None},
    ])
    def test_it_still_serves_a_feed(self, client, history, damage):
        history([self.entry(**damage)])

        response = client.get("/api/changelog.atom")
        assert response.status_code == 200, f"{damage} produced a {response.status_code}"
        assert client.get("/api/changelog").status_code == 200

    @pytest.mark.parametrize("missing_at", [{"at": None}, {"at": ""}, {}])
    def test_updated_is_never_empty(self, client, history, missing_at):
        """`<updated />` is not a Date construct; a strict reader rejects the
        whole document over one malformed entry."""
        import xml.etree.ElementTree as ET

        entry = self.entry(**missing_at)
        entry.pop("at", None) if not missing_at else None
        history([entry])

        feed = ET.fromstring(client.get("/api/changelog.atom").get_data())
        for element in feed.iter(f"{self.NS}updated"):
            assert element.text and element.text.strip(), "an <updated> was empty"

    def test_a_usable_entry_beside_a_damaged_one_still_reads(self, client, history):
        history([self.entry(edited=["junk"]), self.entry(commit="def", added=["Kedro"])])

        import xml.etree.ElementTree as ET
        feed = ET.fromstring(client.get("/api/changelog.atom").get_data())
        summaries = [e.text for e in feed.iter(f"{self.NS}summary")]

        assert any("Added Kedro" in s for s in summaries)


class TestTheQualityEndpoint:
    """`/api/quality` publishes what `make quality-record` measured.

    Served from the recorded file, never computed: measuring means one model
    round trip per agent, which is not something a page load should pay for.
    """

    def _history(self, tmp_path, monkeypatch, *runs):
        import config
        (tmp_path / "quality-history.jsonl").write_text(
            "".join(json.dumps(run) + "\n" for run in runs))
        monkeypatch.setattr(config, "DATA_DIR", tmp_path)

    def test_no_runs_yet_is_an_empty_answer_not_an_error(self, client, tmp_path, monkeypatch):
        import config
        monkeypatch.setattr(config, "DATA_DIR", tmp_path)

        body = client.get('/api/quality').get_json()

        assert body["runs"] == [] and body["latest"] is None
        assert "quality-record" in body["metadata"]["note"]

    def test_it_serves_the_newest_run_first(self, client, tmp_path, monkeypatch):
        self._history(tmp_path, monkeypatch,
                      {"commit": "old", "agents": 300, "limit": 10,
                       "categories": {"Safety": 0.80}},
                      {"commit": "new", "agents": 321, "limit": 10,
                       "categories": {"Safety": 0.90}})

        body = client.get('/api/quality').get_json()

        assert body["latest"]["commit"] == "new"
        assert body["latest"]["agents"] == 321
        assert [r["commit"] for r in body["runs"]] == ["new", "old"]

    def test_it_reports_what_moved(self, client, tmp_path, monkeypatch):
        self._history(tmp_path, monkeypatch,
                      {"commit": "old", "limit": 10, "categories": {"Safety": 0.80}},
                      {"commit": "new", "limit": 10, "categories": {"Safety": 0.90}})

        moved = client.get('/api/quality').get_json()["moved"]

        assert moved == [{"category": "Safety", "from": 0.80, "to": 0.90, "delta": 0.1}]

    def test_two_depths_are_not_compared(self, client, tmp_path, monkeypatch):
        """A run at `--limit 3` cannot see an agent ranked fourth, so the
        difference would be the setting rather than the catalogue."""
        self._history(tmp_path, monkeypatch,
                      {"commit": "old", "limit": 10, "categories": {"Safety": 0.90}},
                      {"commit": "new", "limit": 3, "categories": {"Safety": 0.60}})

        assert client.get('/api/quality').get_json()["moved"] == []

    def test_it_carries_an_etag_like_the_other_reads(self, client, tmp_path, monkeypatch):
        self._history(tmp_path, monkeypatch,
                      {"commit": "a", "limit": 10, "categories": {"Safety": 0.9}})

        first = client.get('/api/quality')
        assert first.headers.get("ETag")

        again = client.get('/api/quality',
                           headers={"If-None-Match": first.headers["ETag"]})
        assert again.status_code == 304


class TestTheQualityEndpointTruncates:
    def test_it_reports_the_true_total_alongside_the_page(self, client, tmp_path, monkeypatch):
        """`read()` caps at MAX_RUNS, and without a total a client cannot
        tell a short history from a truncated one — /api/changelog returns
        both for the same reason."""
        import quality_data

        import config
        runs = [{"commit": f"c{i}", "limit": 10, "categories": {"A": 0.9}}
                for i in range(quality_data.MAX_RUNS + 5)]
        (tmp_path / "quality-history.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in runs))
        monkeypatch.setattr(config, "DATA_DIR", tmp_path)

        meta = client.get('/api/quality').get_json()["metadata"]

        assert meta["count"] == quality_data.MAX_RUNS
        assert meta["total"] == quality_data.MAX_RUNS + 5
