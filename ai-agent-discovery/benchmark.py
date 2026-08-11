"""Measure the hot paths against a real index and a real Ollama.

    python ai-agent-discovery/benchmark.py
    python ai-agent-discovery/benchmark.py --json > before.json
    python ai-agent-discovery/benchmark.py --compare before.json

Numbers here are for spotting regressions between runs on the same machine,
not for comparing across machines. Every search uses a unique query so the
result cache cannot flatter the measurement — an easy mistake, since repeating
one query reports sub-millisecond timings that say nothing about real latency.
"""

import argparse
import json
import os
import statistics
import sys
import time

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), 'backend')))

import config  # noqa: E402
from logging_setup import configure  # noqa: E402


def timed(fn, runs):
    """Return timings in milliseconds."""
    samples = []
    for i in range(runs):
        start = time.perf_counter()
        fn(i)
        samples.append((time.perf_counter() - start) * 1000)
    return samples


def summarize(samples):
    samples = sorted(samples)
    return {
        "runs": len(samples),
        "median_ms": round(statistics.median(samples), 3),
        "p90_ms": round(samples[min(len(samples) - 1, int(len(samples) * 0.9))], 3),
        "max_ms": round(samples[-1], 3),
    }


def measure(runs=15):
    results = {}

    start = time.perf_counter()
    from vectorstore import VectorStore
    results["import_vectorstore"] = {"runs": 1, "median_ms": round((time.perf_counter() - start) * 1000, 3)}

    start = time.perf_counter()
    store = VectorStore()
    results["build_store"] = {"runs": 1, "median_ms": round((time.perf_counter() - start) * 1000, 3)}

    if not store.vector_store:
        print("No index found. Run seed.py first.", file=sys.stderr)
        return None

    store.search("warm up the client", limit=5)

    results["search_uncached"] = summarize(timed(
        lambda i: store.search(f"benchmark probe {i} agents tooling", limit=10), runs))

    store.search("cached probe", limit=10)
    results["search_cached"] = summarize(timed(
        lambda i: store.search("cached probe", limit=10), runs * 3))

    results["get_all_agents"] = summarize(timed(lambda i: store.get_all_agents(), runs * 3))
    results["get_agent"] = summarize(timed(lambda i: store.get_agent("Skyvern"), runs * 3))
    results["get_stats"] = summarize(timed(lambda i: store.get_stats(), runs))
    results["get_tech_stacks"] = summarize(timed(lambda i: store.get_tech_stacks(), runs))

    from embeddings import get_embeddings
    embeddings = get_embeddings()
    results["embed_query"] = summarize(timed(
        lambda i: embeddings.embed_query(f"benchmark probe {i}"), runs))

    results["_meta"] = {
        "agents": store.get_stats().get("count", 0),
        "embedding_model": config.EMBEDDING_MODEL,
    }
    return results


def render(results):
    meta = results.get("_meta", {})
    lines = [f"{meta.get('agents', '?')} agents, embedding model {meta.get('embedding_model', '?')}", ""]
    lines.append(f"{'operation':<20} {'median':>10} {'p90':>10} {'runs':>6}")
    for name, stats in results.items():
        if name.startswith("_"):
            continue
        p90 = f"{stats['p90_ms']:.2f}" if "p90_ms" in stats else "-"
        lines.append(f"{name:<20} {stats['median_ms']:>9.2f}ms {p90:>9}  {stats['runs']:>5}")
    return "\n".join(lines)


def compare(current, baseline):
    """Report how the current run moved against a saved baseline."""
    lines = [f"{'operation':<20} {'baseline':>11} {'current':>11} {'change':>10}"]
    for name, stats in current.items():
        if name.startswith("_") or name not in baseline:
            continue
        before, after = baseline[name]["median_ms"], stats["median_ms"]
        if before <= 0:
            continue
        delta = (after - before) / before * 100
        marker = "  slower" if delta > 20 else ("  faster" if delta < -20 else "")
        lines.append(f"{name:<20} {before:>9.2f}ms {after:>9.2f}ms {delta:>+9.1f}%{marker}")
    return "\n".join(lines)


def scaled_catalogue(target):
    """Repeat the real catalogue up to `target` agents, with distinct names.

    Reusing real descriptions keeps the embeddings representative — random
    strings would cluster differently and make the timings meaningless.
    """
    import json

    with open(config.AGENTS_JSON) as f:
        real = json.load(f)
    if not real:
        raise SystemExit("the catalogue is empty; run seed.py first")

    scaled, copy = [], 0
    while len(scaled) < target:
        for record in real:
            if len(scaled) >= target:
                break
            clone = dict(record)
            if copy:
                clone["name"] = f"{record['name']} v{copy}"
            scaled.append(clone)
        copy += 1
    return scaled


def measure_at_scale(target, runs=15):
    """Time the hot paths against a temporary index of `target` agents."""
    import shutil
    import tempfile

    from models import Agent
    from vectorstore import VectorStore

    agents = [Agent.from_dict(r) for r in scaled_catalogue(target)]
    directory = tempfile.mkdtemp()
    try:
        index_dir = os.path.join(directory, "index")

        start = time.perf_counter()
        VectorStore(persist_directory=index_dir).replace_agents(agents)
        build = (time.perf_counter() - start) * 1000

        start = time.perf_counter()
        store = VectorStore(persist_directory=index_dir)
        load = (time.perf_counter() - start) * 1000

        store.search("warm up", limit=5)
        results = {
            "build_index": {"runs": 1, "median_ms": round(build, 3)},
            "load_index": {"runs": 1, "median_ms": round(load, 3)},
            "search_uncached": summarize(timed(
                lambda i: store.search(f"scale probe {i}", limit=10), runs)),
            "get_all_agents": summarize(timed(lambda i: store.get_all_agents(), runs)),
            "get_agent": summarize(timed(lambda i: store.get_agent(agents[-1].name), runs)),
            "get_stats": summarize(timed(lambda i: store.get_stats(), runs)),
            "_meta": {"agents": target, "embedding_model": config.EMBEDDING_MODEL, "synthetic": True},
        }
        return results
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="benchmark.py", description=__doc__.split("\n")[0])
    parser.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    parser.add_argument("--runs", type=int, default=15, help="samples per operation")
    parser.add_argument("--compare", metavar="FILE", help="compare against a saved JSON run")
    parser.add_argument("--scale", type=int, metavar="N",
                        help="build a throwaway index of N synthetic agents and measure that "
                             "instead, to see how the hot paths behave at a size the catalogue "
                             "has not reached yet")
    args = parser.parse_args(argv)

    configure("WARNING")
    if args.scale:
        print(f"Building a throwaway index of {args.scale} synthetic agents…", file=sys.stderr)
        results = measure_at_scale(args.scale, args.runs)
    else:
        results = measure(args.runs)
    if results is None:
        return 1

    if args.compare:
        with open(args.compare) as f:
            print(compare(results, json.load(f)))
        return 0

    print(json.dumps(results, indent=2) if args.json else render(results))
    return 0


if __name__ == "__main__":
    sys.exit(main())
