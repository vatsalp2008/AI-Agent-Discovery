"""MCP tool logic.

`call_tool` holds the behaviour and is exercised here against the fake store.
The transport layer is a thin typed wrapper over it, verified separately by
driving a real MCP client over stdio.
"""

import importlib.util

import pytest
from conftest import BACKEND

MCP_PATH = BACKEND.parent / "mcp_server.py"


@pytest.fixture
def mcp(store):
    spec = importlib.util.spec_from_file_location("_mcp_server", MCP_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.set_store(store)
    yield module
    module.set_store(None)


def test_every_advertised_tool_is_callable(mcp):
    """A tool in the manifest that call_tool rejects would be a dead entry."""
    for tool in mcp.TOOLS:
        name = tool["name"]
        args = {"query": "x"} if name == "search_agents" else {}
        if name in {"get_agent", "find_similar"}:
            args = {"name": "Cursor"}
        mcp.call_tool(name, args)


def test_search_returns_slim_records(mcp):
    """The full record carries the embedded blob; sending it wastes context."""
    result = mcp.call_tool("search_agents", {"query": "code editor"})
    first = result["results"][0]
    assert set(first) == {"name", "description", "category", "tech_stack",
                          "github_stars", "url", "score", "match"}
    assert "matched_text" not in first
    assert "metadata" not in first


def test_search_splits_the_tech_stack(mcp):
    first = mcp.call_tool("search_agents", {"query": "code editor"})["results"][0]
    assert first["tech_stack"] == ["Electron", "GPT-4"]


def test_search_reports_confidence(mcp):
    assert mcp.call_tool("search_agents", {"query": "code editor"})["confident"] is True


def test_weak_search_says_so(mcp, weak_store):
    mcp.set_store(weak_store)
    result = mcp.call_tool("search_agents", {"query": "banana"})
    assert result["confident"] is False
    assert "closest" in result["note"]


def test_search_requires_a_query(mcp):
    for args in [{}, {"query": ""}, {"query": "   "}]:
        with pytest.raises(ValueError, match="required"):
            mcp.call_tool("search_agents", args)


def test_search_limit_is_capped(mcp):
    import config

    result = mcp.call_tool("search_agents", {"query": "x", "limit": 10_000})
    assert len(result["results"]) <= config.SEARCH_MAX_LIMIT


def test_search_honours_the_category_filter(mcp):
    result = mcp.call_tool("search_agents", {"query": "agent", "category": "Research"})
    assert all(r["category"] == "Research" for r in result["results"])


def test_get_agent_is_case_insensitive(mcp):
    assert mcp.call_tool("get_agent", {"name": "cursor"})["name"] == "Cursor"


def test_get_agent_rejects_an_unknown_name(mcp):
    with pytest.raises(ValueError, match="No agent named"):
        mcp.call_tool("get_agent", {"name": "Nope"})


def test_find_similar_excludes_the_agent(mcp):
    result = mcp.call_tool("find_similar", {"name": "Cursor"})
    assert "Cursor" not in [r["name"] for r in result["results"]]
    assert result["of"] == "Cursor"


def test_find_similar_rejects_an_unknown_name(mcp):
    with pytest.raises(ValueError, match="No agent named"):
        mcp.call_tool("find_similar", {"name": "Nope"})


def test_list_categories(mcp):
    names = [c["name"] for c in mcp.call_tool("list_categories")["categories"]]
    assert "Code Generation" in names


def test_list_technologies(mcp):
    names = [t["name"] for t in mcp.call_tool("list_technologies")["technologies"]]
    assert "Python" in names


def test_catalogue_stats(mcp):
    assert mcp.call_tool("catalogue_stats")["count"] == 3


def test_unknown_tool_is_rejected(mcp):
    with pytest.raises(ValueError, match="Unknown tool"):
        mcp.call_tool("definitely_not_a_tool", {})


def test_no_tool_mutates_the_catalogue(mcp):
    """An agent querying this should not be able to rewrite the index."""
    names = {t["name"] for t in mcp.TOOLS}
    assert not any(w in n for n in names for w in ("add", "delete", "update", "write", "seed"))


def test_repo_registration_points_at_the_server(mcp):
    """.mcp.json lets an MCP client pick this up without manual setup."""
    import json

    from conftest import REPO_ROOT

    config_path = REPO_ROOT / ".mcp.json"
    assert config_path.exists(), ".mcp.json is missing"

    servers = json.loads(config_path.read_text())["mcpServers"]
    entry = servers["agent-discovery"]
    script = REPO_ROOT / entry["args"][0]
    assert script.exists(), f"{entry['args'][0]} does not exist"
    assert script.name == "mcp_server.py"


class TestUnusableIndex:
    """An unseeded index must be an error, not "nothing matched".

    A tool error prompts the user to fix their setup; an empty result set
    makes the calling model state that no such tools exist.
    """

    @pytest.fixture
    def unseeded(self, mcp, tmp_path):
        from vectorstore import VectorStore

        mcp.set_store(VectorStore(persist_directory=tmp_path / "none", embedding_function=object()))
        return mcp

    def test_search_reports_a_setup_problem(self, unseeded):
        with pytest.raises(ValueError, match="Run seed.py"):
            unseeded.call_tool("search_agents", {"query": "code editor"})

    def test_every_tool_reports_it(self, unseeded):
        for name, args in [("get_agent", {"name": "X"}), ("list_categories", {}),
                           ("catalogue_stats", {}), ("find_similar", {"name": "X"})]:
            with pytest.raises(ValueError, match="No agent index"):
                unseeded.call_tool(name, args)

    def test_a_stale_model_names_the_mismatch(self, mcp, tmp_path):
        from vectorstore import VectorStore

        store = VectorStore(persist_directory=tmp_path / "none", embedding_function=object())
        store.stale_model = "llama3.2"
        mcp.set_store(store)

        with pytest.raises(ValueError, match="llama3.2"):
            mcp.call_tool("search_agents", {"query": "x"})

    def test_a_seeded_index_is_unaffected(self, mcp):
        assert mcp.call_tool("search_agents", {"query": "code editor"})["results"]


def test_the_entry_point_persists_the_embedding_cache():
    """cli.py and the Flask app both do; this one used to be forgotten."""
    source = MCP_PATH.read_text()
    assert "atexit.register" in source
    assert "save_cache" in source


def test_search_says_which_kind_of_match_it_is(mcp):
    """A name match scores 1.0 for a different reason than a close semantic
    match; a calling model that cannot distinguish them would overstate it."""
    results = mcp.call_tool("search_agents", {"query": "code editor"})["results"]
    assert all(r["match"] == "semantic" for r in results)

    exact = mcp.call_tool("search_agents", {"query": "Cursor"})["results"]
    assert exact[0]["name"] == "Cursor"
    assert exact[0]["match"] == "name"


def test_get_agent_carries_no_match_label(mcp):
    """It was fetched by name, not ranked, so there is no score to qualify."""
    assert "match" not in mcp.call_tool("get_agent", {"name": "Cursor"})


class TestProjectHealth:
    """A model recommending an archived project without knowing it is
    archived is the failure the status field exists to prevent."""

    def result(self, **metadata):
        base = {"name": "Thing", "category": "Safety", "stack": "Python",
                "stars": 1, "description": "Does a thing.", "url": "https://e.com"}
        base.update(metadata)
        return {"name": "Thing", "metadata": base}

    def test_an_archived_project_says_so(self, mcp):
        assert mcp._slim(self.result(status="archived"))["status"] == "archived"

    def test_a_dormant_one_too(self, mcp):
        assert mcp._slim(self.result(status="dormant"))["status"] == "dormant"

    def test_a_healthy_project_spends_no_tokens_saying_so(self, mcp):
        """204 of 223 entries are active; a field repeating that on every
        result is context the caller pays for and cannot use."""
        assert "status" not in mcp._slim(self.result())
        assert "status" not in mcp._slim(self.result(status="active"))


def test_search_can_leave_out_abandoned_projects(mcp, store):
    """Worth doing when the answer is a recommendation rather than a survey."""
    seen = {}
    real = store.search
    store.search = lambda q, **kw: (seen.update(kw), real(q, **kw))[1]

    mcp.call_tool("search_agents", {"query": "agent", "maintained": True})
    assert seen["maintained"] is True

    mcp.call_tool("search_agents", {"query": "agent"})
    assert seen["maintained"] is False


def test_every_declared_search_argument_reaches_the_store(mcp, store):
    """A client reads inputSchema to know what it may send, so an argument
    the wrapper honours but the schema omits is one no caller will ever pass
    — and one the schema declares but the wrapper drops is a lie.
    """
    declared = next(t for t in mcp.TOOLS if t["name"] == "search_agents")
    properties = set(declared["inputSchema"]["properties"]) - {"query", "limit"}

    seen = {}
    real = store.search
    store.search = lambda q, **kw: (seen.update(kw), real(q, **kw))[1]

    sent = {"query": "agent", "category": "Code Generation",
            "min_score": 0.1, "maintained": True}
    mcp.call_tool("search_agents", sent)

    missing = [name for name in properties if name not in seen]
    assert not missing, f"declared but never passed to the store: {missing}"
    assert seen["maintained"] is True
