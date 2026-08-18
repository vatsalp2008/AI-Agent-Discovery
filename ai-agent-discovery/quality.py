"""Measure how well the catalogue answers questions about itself.

    python ai-agent-discovery/quality.py
    python ai-agent-discovery/quality.py --category Robotics
    python ai-agent-discovery/quality.py --json > quality.json

Two numbers, because two different things go wrong as a catalogue grows.

**Self-retrieval.** Ask for each agent using its own `use_case` and see where
it ranks. An agent that cannot be found by a plain description of what it does
is, for practical purposes, not in the catalogue. Reported per category as a
mean reciprocal rank, because the weakness is rarely one entry — it is a
crowded neighbourhood where thirty tools all say "fine-tune a model".

Read a low score as "look at this", not as "this is broken". Two tools that
genuinely do the same job compete for the same words, and one of them has to
come second: Apache Airflow loses "Scheduling data and ML pipelines" to Mage,
whose own use case is a near-verbatim restatement of it. That is the metric
working, not a defect in either entry. What it is good at is the other case —
an entry whose wording says nothing specific at all, like TransformerLens
under "Understanding what a model has learned".

**Guard margin.** For each case in the live retrieval suite, the gap between
the best expected result and the best result that would fail it. A guard
passing by 0.002 is not a guard; it is a coin that has landed the same way so
far. `"fine tune a model on one GPU"` sat at exactly that margin for weeks,
and the next agent added to the catalogue broke it — which read as a
regression from the change, when the change had only exposed it.

This is a measurement, not a test. Nothing here fails a build: the scores are
a property of the catalogue and of the embedding model, and the useful signal
is how they move between runs, not whether they clear some absolute bar.
"""

import argparse
import json
import os
import re
import sys
from collections import defaultdict

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), 'backend')))

import config  # noqa: E402
from logging_setup import configure  # noqa: E402
from scraper import load_agents  # noqa: E402
from vectorstore import VectorStore  # noqa: E402

# How thin a guard's margin has to be before it is worth reporting. Set from
# the one that actually broke: 0.002 was invisible until it cost a session.
THIN_MARGIN = 0.02

# Where the live suite keeps its query/expected pairs. Read rather than
# duplicated — a second copy of the ground truth would drift from the first,
# and then this tool would be reassuring about a suite it no longer describes.
GUARDS = "tests-live/test_live_ollama.py"


def rank_of(results, wanted):
    """1-based rank of the first result in `wanted`, or None."""
    for position, result in enumerate(results, start=1):
        if result["name"] in wanted:
            return position
    return None


def self_retrieval(store, agents, limit=10):
    """Where each agent ranks when asked for in its own words."""
    rows = []
    for agent in agents:
        # use_case rather than the description: it is the shorter, more
        # question-shaped of the two, and closer to what someone would type.
        query = agent.use_case or agent.description
        results = store.search(query, limit=limit)
        position = rank_of(results, {agent.name})
        rows.append({
            "name": agent.name,
            "category": agent.category,
            "rank": position,
            "reciprocal": 1 / position if position else 0.0,
            "beaten_by": [r["name"] for r in results[:3] if r["name"] != agent.name][:2],
        })
    return rows


def by_category(rows):
    """Mean reciprocal rank per category, weakest first."""
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["category"]].append(row["reciprocal"])

    summary = [{"category": category,
                "agents": len(scores),
                "mrr": round(sum(scores) / len(scores), 3),
                "unfindable": sum(1 for s in scores if s == 0.0)}
               for category, scores in grouped.items()]
    return sorted(summary, key=lambda row: row["mrr"])


def read_guards(path=None):
    """The live suite's (query, expected) pairs, parsed from its source.

    Importing the module would pull in pytest fixtures and a live Ollama
    connection at import time; the cases are a literal list, so reading them
    is both cheaper and harder to break.
    """
    source = (config.REPO_ROOT / (path or GUARDS)).read_text()
    cases = []
    for query, names in re.findall(r'\(\s*"([^"]+)",\s*\{([^}]+)\}\s*\)', source):
        expected = set(re.findall(r'"([^"]+)"', names))
        if expected:
            cases.append((query, expected))
    return cases


def guard_margins(store, cases, limit=10):
    """How close each guard case is to failing.

    The margin is the expected agent's score minus the score of the best
    result that is *not* expected and ranks high enough to displace it. A
    negative margin means the case is already failing.
    """
    rows = []
    for query, expected in cases:
        results = store.search(query, limit=limit)
        if not results:
            rows.append({"query": query, "rank": None, "margin": None,
                         "expected": sorted(expected), "rival": None})
            continue

        hit = next((r for r in results if r["name"] in expected), None)
        # The rival is whatever would take third place if the expected agent
        # slipped one position — the live suite asserts a top-3 finish.
        #
        # None, not the weakest result, when fewer than three others came
        # back: nothing there can displace the expected agent from the top
        # three, so there is no margin to report. Falling back to `others[-1]`
        # measured the gap to a result that could never take the place, which
        # understated it and flagged comfortable guards as thin — every one of
        # them under `--limit 3`, the limit the live suite itself uses.
        others = [r for r in results if r["name"] not in expected]
        rival = others[2] if len(others) > 2 else None

        rows.append({
            "query": query,
            "rank": rank_of(results, expected),
            "score": round(hit["score"], 4) if hit else None,
            "margin": round(hit["score"] - rival["score"], 4) if hit and rival else None,
            "rival": rival["name"] if rival else None,
            "expected": sorted(expected),
        })
    return rows


def render(categories, weakest, guards, thin_margin=THIN_MARGIN):
    out = ["# Retrieval quality", ""]

    out.append("## Self-retrieval by category")
    out.append("")
    out.append("Asking for each agent in its own words, and seeing where it lands.")
    out.append("")
    out.append("| Category | Agents | MRR | Not in top 10 |")
    out.append("| --- | ---: | ---: | ---: |")
    for row in categories:
        out.append(f"| {row['category']} | {row['agents']} | {row['mrr']:.3f} "
                   f"| {row['unfindable']} |")
    out.append("")

    if weakest:
        out.append("## Agents their own description does not find")
        out.append("")
        for row in weakest:
            beaten = ", ".join(row["beaten_by"]) or "—"
            where = row["rank"] or "outside the top 10"
            out.append(f"- **{row['name']}** ({row['category']}) — {where}; "
                       f"loses to {beaten}")
        out.append("")

    # A negative margin means the guard is already failing, and it is listed
    # as such below; counting it here as well would report it twice and read
    # as "passes by -0.2".
    at_risk = [g for g in guards
               if g["margin"] is not None and 0 <= g["margin"] < thin_margin]
    failing = [g for g in guards if g["rank"] is None or g["rank"] > 3]

    out.append("## Guards")
    out.append("")
    if failing:
        out.append(f"**{len(failing)} failing now:**")
        for guard in failing:
            out.append(f"- `{guard['query']}` — expected one of "
                       f"{', '.join(guard['expected'])}")
        out.append("")
    out.append(f"{len(at_risk)} of {len(guards)} pass by less than {thin_margin}:")
    out.append("")
    if at_risk:
        out.append("| Query | Rank | Margin | Next in line |")
        out.append("| --- | ---: | ---: | --- |")
        for guard in sorted(at_risk, key=lambda g: g["margin"]):
            out.append(f"| {guard['query']} | {guard['rank']} "
                       f"| {guard['margin']:+.4f} | {guard['rival']} |")
    else:
        out.append("None — every guard has room.")
    return "\n".join(out) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(prog="quality.py",
                                     description=__doc__.split("\n")[0])
    parser.add_argument("--category", help="only measure agents in this category")
    parser.add_argument("--limit", type=int, default=10,
                        help="how deep to look for each agent (default: 10)")
    parser.add_argument("--worst", type=int, default=15,
                        help="how many weak entries to list (default: 15)")
    parser.add_argument("--thin-margin", type=float, default=THIN_MARGIN,
                        help=f"report guards passing by less (default: {THIN_MARGIN})")
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--out", help="write the report here instead of stdout")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    configure("DEBUG" if args.verbose else "WARNING")

    agents = load_agents()
    if args.category:
        wanted = args.category.casefold()
        agents = [a for a in agents if (a.category or "").casefold() == wanted]
        if not agents:
            print(f"No agents in category {args.category!r}.", file=sys.stderr)
            return 1

    store = VectorStore()
    if not store.vector_store:
        print("No index to measure. Run `make seed` first.", file=sys.stderr)
        return 1

    rows = self_retrieval(store, agents, limit=args.limit)
    categories = by_category(rows)
    weakest = sorted((r for r in rows if r["rank"] != 1),
                     key=lambda r: (r["reciprocal"], r["name"]))[:args.worst]
    guards = guard_margins(store, read_guards(), limit=args.limit)

    if args.as_json:
        report = json.dumps({"categories": categories, "agents": rows,
                             "guards": guards}, indent=2)
    else:
        report = render(categories, weakest, guards, args.thin_margin)

    if args.out:
        with open(args.out, "w") as f:
            f.write(report if report.endswith("\n") else report + "\n")
        print(f"Wrote {args.out}", file=sys.stderr)
    else:
        print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
