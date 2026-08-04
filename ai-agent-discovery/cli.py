"""Search the agent index from the terminal.

    python cli.py "an agent that writes python"
    python cli.py "chatbot" --category "Customer Service" --limit 3
    python cli.py --list
    python cli.py --stats

Useful for checking the index without starting the web server.
"""

import argparse
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
    parser.add_argument("-l", "--list", action="store_true", dest="list_agents",
                        help="list every indexed agent and exit")
    parser.add_argument("-s", "--stats", action="store_true",
                        help="show index statistics and exit")
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


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    if not (args.query or args.list_agents or args.stats):
        parser.print_help()
        return 2

    configure("DEBUG" if args.verbose else "WARNING")

    from vectorstore import VectorStore
    store = VectorStore()

    if store.stale_model:
        print(
            f"Index was built with embedding model {store.stale_model!r} but "
            f"{config.EMBEDDING_MODEL!r} is configured. Re-run seed.py.",
            file=sys.stderr,
        )
        return 1

    if args.stats:
        print(format_stats(store.get_stats()))
        return 0

    if args.list_agents:
        agents = store.get_all_agents()
        if not agents:
            print("No agents indexed. Run seed.py first.", file=sys.stderr)
            return 1
        for agent in agents:
            print(f"{agent['name']:<20} {agent['metadata'].get('category', '')}")
        return 0

    results = store.search(args.query, limit=args.limit, category=args.category)
    if not results and not store.vector_store:
        print("No agents indexed. Run seed.py first.", file=sys.stderr)
        return 1

    print(format_results(results))
    return 0


if __name__ == "__main__":
    sys.exit(main())
