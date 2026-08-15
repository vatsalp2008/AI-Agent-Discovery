"""Expose the agent index to other AI agents over MCP.

    python ai-agent-discovery/mcp_server.py

Speaks MCP over stdio, so it plugs into any MCP client. Register it with
Claude Code as:

    claude mcp add agent-discovery -- python /path/to/ai-agent-discovery/mcp_server.py

The tools mirror the HTTP API, minus anything that mutates: an agent querying
this should be able to read the catalogue, not rewrite it.
"""

import asyncio
import atexit
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), 'backend')))

import config  # noqa: E402
from logging_setup import configure  # noqa: E402

# Lazily built so a client that only lists tools never pays for the index.
_store = None


def get_store():
    global _store
    if _store is None:
        from vectorstore import VectorStore

        _store = VectorStore()
    return _store


def set_store(store):
    """Override the store. Used by tests."""
    global _store
    _store = store


# The tool surface, kept for documentation and tests. The live schemas are
# derived from the typed wrappers in build_server().
TOOLS = [
    {
        "name": "search_agents",
        "description": (
            "Search the AI agent catalogue by natural language. Returns agents "
            "ranked by semantic similarity, each with a 0-1 relevance score."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What you need an agent to do"},
                "limit": {"type": "integer", "description": "Maximum results (default 5)"},
                "category": {"type": "string", "description": "Restrict to one category"},
                "min_score": {
                    "type": "number",
                    "description": "Drop results below this relevance score (0-1)",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_agent",
        "description": "Fetch one agent by name (case-insensitive).",
        "inputSchema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    },
    {
        "name": "list_categories",
        "description": "List the catalogue's categories with agent counts.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "list_technologies",
        "description": "List the technologies used across the catalogue, with counts.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "find_similar",
        "description": "Find agents similar to a named one, excluding it.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "limit": {"type": "integer", "description": "Maximum results (default 3)"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "catalogue_stats",
        "description": "Summarize the index: agent count, categories, stars, build time.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def _slim(result):
    """Trim a search result to what a calling agent actually needs.

    The raw record carries the full embedded text and a duplicate metadata
    block; sending those wastes the caller's context window.
    """
    meta = result.get("metadata", {})
    slim = {
        "name": result.get("name"),
        "description": meta.get("description") or result.get("description", ""),
        "category": meta.get("category"),
        "tech_stack": [t.strip() for t in str(meta.get("stack") or "").split(",") if t.strip()],
        "github_stars": meta.get("stars"),
        "url": meta.get("url"),
    }
    # Only when it is not the default, for the same reason the badge is only
    # shown then — but it must be *present* when it matters: a model
    # recommending an archived project without knowing it is archived is the
    # failure this field exists to prevent.
    status = meta.get("status")
    if status and status != "active":
        slim["status"] = status
    if "score" in result:
        slim["score"] = round(result["score"], 4)
        # Say which kind of match this is. A name match scores 1.0 because the
        # query was the agent's name, not because the embedding ranked it top;
        # a calling model that cannot tell them apart would overstate it.
        slim["match"] = result.get("match", "semantic")
    return slim


def _require_index(store):
    """Fail loudly when there is no usable index.

    Otherwise an unseeded checkout answers every search with "nothing matched",
    and the calling model reports that no such tools exist — a confident wrong
    answer, where an error would have prompted the user to seed. The HTTP layer
    already distinguishes these with a 503 on /api/health.
    """
    if store.vector_store is not None:
        return
    if getattr(store, "stale_model", None):
        raise ValueError(
            f"The index was built with embedding model {store.stale_model!r} but "
            f"{config.EMBEDDING_MODEL!r} is configured. Re-run seed.py to rebuild it. "
            "This is a setup problem, not an empty catalogue."
        )
    raise ValueError(
        "No agent index is available. Run seed.py to build one. "
        "This is a setup problem, not an empty catalogue."
    )


def call_tool(name, arguments=None):
    """Run a tool and return a JSON-serializable result.

    Raises ValueError for anything the caller got wrong, so the transport
    layer can report it as a tool error rather than crashing the server.
    """
    arguments = arguments or {}
    store = get_store()
    _require_index(store)

    if name == "search_agents":
        query = (arguments.get("query") or "").strip()
        if not query:
            raise ValueError("'query' is required")

        limit = int(arguments.get("limit") or 5)
        results = store.search(
            query,
            limit=max(1, min(limit, config.SEARCH_MAX_LIMIT)),
            category=arguments.get("category"),
            min_score=arguments.get("min_score"),
        )
        confident = bool(results) and results[0]["score"] >= config.SEARCH_MIN_SCORE
        return {
            "query": query,
            "confident": confident,
            "note": None if confident else "No agent matched this query well; these are the closest.",
            "results": [_slim(r) for r in results],
        }

    if name == "get_agent":
        agent_name = (arguments.get("name") or "").strip()
        if not agent_name:
            raise ValueError("'name' is required")
        agent = store.get_agent(agent_name)
        if agent is None:
            raise ValueError(f"No agent named {agent_name!r}")
        return _slim(agent)

    if name == "list_categories":
        return {"categories": store.get_categories()}

    if name == "list_technologies":
        return {"technologies": store.get_tech_stacks()}

    if name == "find_similar":
        agent_name = (arguments.get("name") or "").strip()
        if not agent_name:
            raise ValueError("'name' is required")
        limit = max(1, min(int(arguments.get("limit") or 3), config.SEARCH_MAX_LIMIT))
        similar = store.find_similar(agent_name, limit=limit)
        if similar is None:
            raise ValueError(f"No agent named {agent_name!r}")
        return {"of": agent_name, "results": [_slim(r) for r in similar]}

    if name == "catalogue_stats":
        return store.get_stats()

    raise ValueError(f"Unknown tool: {name}")


def build_server():
    """Register the tools on an MCPServer.

    The schemas come from the type hints and docstrings below rather than
    being hand-written, so they cannot drift from what the functions accept.
    Each wrapper is a thin shell over `call_tool`, which holds the logic and
    is what the tests exercise.
    """
    from mcp.server import MCPServer

    mcp = MCPServer(
        name="agent-discovery",
        instructions=(
            "Search a curated catalogue of AI agents, frameworks and developer "
            "tools by describing what you need in plain language."
        ),
    )

    async def _run(name, arguments):
        # Off the event loop: a search embeds the query over HTTP, which would
        # otherwise stall every other request the client has in flight.
        return await asyncio.to_thread(call_tool, name, arguments)

    @mcp.tool()
    async def search_agents(query: str, limit: int = 5, category: str | None = None,
                            min_score: float | None = None) -> dict:
        """Search the AI agent catalogue by natural language.

        Returns agents ranked by semantic similarity, each with a 0-1
        relevance score. When nothing matches well the response says so
        rather than presenting weak results as answers.
        """
        return await _run("search_agents", {
            "query": query, "limit": limit,
            "category": category, "min_score": min_score,
        })

    @mcp.tool()
    async def get_agent(name: str) -> dict:
        """Fetch one agent by name (case-insensitive)."""
        return await _run("get_agent", {"name": name})

    @mcp.tool()
    async def list_categories() -> dict:
        """List the catalogue's categories with agent counts."""
        return await _run("list_categories", {})

    @mcp.tool()
    async def list_technologies() -> dict:
        """List the technologies used across the catalogue, with counts."""
        return await _run("list_technologies", {})

    @mcp.tool()
    async def find_similar(name: str, limit: int = 3) -> dict:
        """Find agents similar to a named one, excluding it."""
        return await _run("find_similar", {"name": name, "limit": limit})

    @mcp.tool()
    async def catalogue_stats() -> dict:
        """Summarize the index: agent count, categories, stars, build time."""
        return await _run("catalogue_stats", {})

    return mcp


def main():
    # stdout carries the protocol, so logs must not go there.
    configure("WARNING")

    # Same as cli.py and the Flask app: flush the query-embedding cache on the
    # way out, or this entry point never benefits from it across runs.
    import embeddings
    atexit.register(embeddings.save_cache)

    build_server().run(transport="stdio")
    return 0


if __name__ == "__main__":
    sys.exit(main())
