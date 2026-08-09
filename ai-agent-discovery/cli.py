"""Search the agent index from the terminal.

    python cli.py "an agent that writes python"
    python cli.py "chatbot" --category "Customer Service" --limit 3
    python cli.py --list
    python cli.py --stats
    python cli.py "rag" --json | jq '.results[].name'

Useful for checking the index without starting the web server.
"""

import argparse
import atexit
import json
import os
import sys

# Add backend to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), 'backend')))

import config  # noqa: E402
from logging_setup import configure  # noqa: E402


def build_parser():
    parser = argparse.ArgumentParser(
        prog="cli.py",
        description="Semantic search over the local AI agent index.",
    )
    parser.add_argument("query", nargs="?", help="natural language search query")
    parser.add_argument("-n", "--limit", type=int, default=config.SEARCH_DEFAULT_LIMIT,
                        help=f"maximum results (default: {config.SEARCH_DEFAULT_LIMIT})")
    parser.add_argument("-c", "--category", help="restrict results to one category")
    parser.add_argument("-t", "--tech", help="restrict results to one technology")
    parser.add_argument("--sort", choices=["name", "stars", "category"], default="name",
                        help="sort order for --list (default: name)")
    parser.add_argument("--order", choices=["asc", "desc"],
                        help="sort direction (default: desc for stars, asc otherwise)")
    parser.add_argument("--min-score", type=float, dest="min_score",
                        help="drop results below this relevance score (0-1)")
    parser.add_argument("-l", "--list", action="store_true", dest="list_agents",
                        help="list every indexed agent and exit")
    parser.add_argument("-s", "--stats", action="store_true",
                        help="show index statistics and exit")
    parser.add_argument("--tech-list", action="store_true", dest="tech_list",
                        help="list technologies across the catalogue and exit")
    parser.add_argument("--summarize", action="store_true",
                        help="add an AI overview of the results")
    parser.add_argument("--json", action="store_true", dest="as_json",
                        help="emit JSON instead of formatted text")
    parser.add_argument("-v", "--verbose", action="store_true", help="show debug logging")
    return parser


def format_stars(stars):
    stars = int(stars or 0)
    if stars >= 1000:
        return f"{stars / 1000:.1f}k"
    return str(stars)


def format_result(index, result):
    meta = result.get("metadata", {})
    header = f"{index}. {result.get('name', 'Unknown')}"
    if "score" in result:
        header += f"  [{result['score'] * 100:.0f}% match]"
    return "\n".join([
        header,
        f"   {meta.get('category', 'Uncategorized')} · {format_stars(meta.get('stars'))} stars",
        f"   {meta.get('description', '')}".rstrip(),
        f"   {meta.get('url', '')}".rstrip(),
    ])


def format_results(results):
    if not results:
        return "No matching agents found."
    return "\n\n".join(format_result(i, r) for i, r in enumerate(results, start=1))


def format_stats(stats):
    top = stats.get("top_category") or {}
    return "\n".join([
        f"Indexed agents : {stats.get('count', 0)}",
        f"Categories     : {stats.get('categories', 0)}",
        f"Top category   : {top.get('name', 'N/A')} ({top.get('count', 0)})",
        f"Total stars    : {stats.get('total_stars', 0):,}",
        f"Embedding model: {stats.get('embedding_model', 'unknown')}",
    ])


# Mirrors AGENT_SORTS in the API so the two stay consistent.
SORT_KEYS = {
    "name": (lambda a: (a["name"] or "").casefold(), "asc"),
    "stars": (lambda a: int(a["metadata"].get("stars") or 0), "desc"),
    "category": (lambda a: ((a["metadata"].get("category") or "").casefold(),
                            (a["name"] or "").casefold()), "asc"),
}


def sort_agents(agents, sort="name", order=None):
    """Return `agents` sorted, defaulting stars to descending."""
    key, default_order = SORT_KEYS[sort]
    return sorted(agents, key=key, reverse=(order or default_order) == "desc")


def filter_agents(agents, category=None, tech=None):
    """Narrow a list of agents by category and/or technology."""
    if category:
        wanted = category.strip().casefold()
        agents = [a for a in agents if (a["metadata"].get("category") or "").casefold() == wanted]
    if tech:
        wanted = tech.strip().casefold()
        agents = [
            a for a in agents
            if wanted in {t.strip().casefold() for t in str(a["metadata"].get("stack") or "").split(",")}
        ]
    return agents


def _build_store():
    """Construct the vector store. Separated so tests can substitute a fake."""
    from vectorstore import VectorStore

    return VectorStore()


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    if not (args.query or args.list_agents or args.stats or args.tech_list):
        parser.print_help()
        return 2

    configure("DEBUG" if args.verbose else "WARNING")

    store = _build_store()
    # The CLI is short-lived, so persist whatever it embedded before exiting.
    import embeddings
    atexit.register(embeddings.save_cache)

    if store.stale_model:
        print(
            f"Index was built with embedding model {store.stale_model!r} but "
            f"{config.EMBEDDING_MODEL!r} is configured. Re-run seed.py.",
            file=sys.stderr,
        )
        return 1

    if args.stats:
        stats = store.get_stats()
        print(json.dumps(stats, indent=2) if args.as_json else format_stats(stats))
        return 0

    if args.tech_list:
        tech = store.get_tech_stacks()
        if args.as_json:
            print(json.dumps(tech, indent=2))
        else:
            for entry in tech:
                print(f"{entry['name']:<20} {entry['count']}")
        return 0

    if args.list_agents:
        agents = filter_agents(store.get_all_agents(), args.category, args.tech)
        agents = sort_agents(agents, args.sort, args.order)
        if not agents:
            print("No matching agents.", file=sys.stderr)
            return 1
        if args.as_json:
            print(json.dumps(agents, indent=2))
        else:
            for agent in agents:
                stars = format_stars(agent["metadata"].get("stars"))
                print(f"{agent['name']:<20} {agent['metadata'].get('category', ''):<20} {stars:>7}")
        return 0

    results = store.search(
        args.query, limit=args.limit, category=args.category, min_score=args.min_score
    )
    if args.tech:
        results = filter_agents(results, tech=args.tech)
    if not results and not store.vector_store:
        print("No agents indexed. Run seed.py first.", file=sys.stderr)
        return 1

    summary = None
    if args.summarize:
        import generation
        summary = generation.summarize(args.query, results)
        if summary is None:
            print("Could not generate an overview; showing results only.", file=sys.stderr)

    if args.as_json:
        print(json.dumps({"query": args.query, "results": results, "summary": summary}, indent=2))
        return 0

    if summary:
        print(summary)
        print()
    print(format_results(results))
    return 0


if __name__ == "__main__":
    sys.exit(main())
