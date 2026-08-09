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
                          "github_stars", "url", "score"}
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
