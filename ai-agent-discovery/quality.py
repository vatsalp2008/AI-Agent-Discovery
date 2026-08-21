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
import logging
import os
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), 'backend')))

import quality_data  # noqa: E402
from quality_data import DEFAULT_LIMIT, NOTABLE_MOVE  # noqa: E402

import config  # noqa: E402
from logging_setup import configure  # noqa: E402
from scraper import load_agents  # noqa: E402
from vectorstore import VectorStore  # noqa: E402

logger = logging.getLogger(__name__)

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


def self_retrieval(store, agents, limit=DEFAULT_LIMIT):
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


def guard_margins(store, cases, limit=DEFAULT_LIMIT):
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


def history_path():
    """Deferred to quality_data, which honours DATA_DIR.

    Resolving it here as REPO_ROOT/data meant a deployment that sets the
    documented DATA_DIR wrote runs to one file and served /api/quality from
    another — so the panel stayed empty forever, which is exactly the drift
    the shared module was introduced to prevent.
    """
    return quality_data.path()


def read_history(path=None):
    """Previously recorded runs, oldest first.

    Delegates to quality_data rather than repeating its parse. The two copies
    had already diverged on what counts as a run — quality_data required a
    `categories` dict, this accepted any object — so `make quality` and
    /api/quality could disagree about how many runs existed, which is the
    drift sharing the path was meant to end.
    """
    # Resolved here, not left to quality_data's own default: history_path()
    # is what tests and callers override.
    return quality_data.read(limit=None, where=path or history_path(),
                             newest_first=False)


def record(categories, guards, agents, limit, path=None):
    """Append this run to the history and return what was written."""
    measured = [g for g in guards if g["margin"] is not None]
    run = {
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "commit": _commit(),
        "agents": agents,
        # Recorded because it changes the numbers: a run at --limit 3 cannot
        # see an agent ranked fourth, so every reciprocal is that much lower.
        # Comparing across limits would report the setting as a change in the
        # catalogue.
        "limit": limit,
        "categories": {row["category"]: row["mrr"] for row in categories},
        "guards": len(guards),
        "thinnest": min((g["margin"] for g in measured), default=None),
        "failing": sum(1 for g in guards
                       if g["rank"] is None or g["rank"] > 3),
    }
    where = path or history_path()
    # Created if absent: the path follows DATA_DIR now rather than the
    # always-present repository directory, and this append happens *after*
    # one embedding round trip per agent — losing the measurement to a
    # missing directory would waste the whole run.
    where.parent.mkdir(parents=True, exist_ok=True)
    with open(where, "a") as f:
        f.write(json.dumps(run) + "\n")
    return run


def _commit():
    """The commit the scores describe, so a move can be traced to a change."""
    try:
        found = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                               cwd=config.REPO_ROOT, capture_output=True,
                               text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return found.stdout.strip() or None if found.returncode == 0 else None


def comparable(history, limit):
    """The newest recorded run measured at the same depth, if there is one.

    Taking simply the last line meant one `--record --limit 3` blinded every
    later default run: it mismatched, movement returned nothing, and a
    perfectly comparable run sat one line above it unused.
    """
    for run in reversed(history or []):
        if run.get("limit", DEFAULT_LIMIT) == limit:
            return run
    return None


def movement(current, previous, notable=NOTABLE_MOVE, limit=None):
    """Categories that moved since the last recorded run, biggest fall first.

    Both directions are reported. A category climbing is worth seeing too:
    it is usually somebody's wording fix working, and the alternative is
    only ever hearing bad news.
    """
    if previous and limit is not None:
        # Absent means a run recorded before the field existed, and every one
        # of those was taken at the default — so default it, rather than
        # treating "unknown" as "matches whatever you are asking for". Read
        # as None, a legacy line reported a 0.376 collapse in Safety that was
        # entirely the effect of `--limit 3`.
        if previous.get("limit", DEFAULT_LIMIT) != limit:
            return []

    # The shared rule, so the CLI and the page cannot answer "what moved"
    # differently — they did, and the rounding fix had to be written twice.
    return quality_data.moves_between((previous or {}).get("categories"),
                                      {row["category"]: row["mrr"] for row in current},
                                      notable)


def render(categories, weakest, guards, thin_margin=THIN_MARGIN, moves=None,
           previous=None, limit=DEFAULT_LIMIT, history=None, partial=False):
    out = ["# Retrieval quality", ""]

    out.append("## Self-retrieval by category")
    out.append("")
    out.append("Asking for each agent in its own words, and seeing where it lands.")
    out.append("")
    out.append(f"| Category | Agents | MRR | Not in top {limit} |")
    out.append("| --- | ---: | ---: | ---: |")
    for row in categories:
        out.append(f"| {row['category']} | {row['agents']} | {row['mrr']:.3f} "
                   f"| {row['unfindable']} |")
    out.append("")

    if weakest:
        out.append("## Agents their own use case does not find")
        out.append("")
        for row in weakest:
            beaten = ", ".join(row["beaten_by"]) or "—"
            where = row["rank"] or f"outside the top {limit}"
            out.append(f"- **{row['name']}** ({row['category']}) — {where}; "
                       f"loses to {beaten}")
        out.append("")

    # A negative margin means the guard is already failing, and it is listed
    # as such below; counting it here as well would report it twice and read
    # as "passes by -0.2".
    failing = [g for g in guards if g["rank"] is None or g["rank"] > 3]

    # Counted against the guards actually measured, not against all of them.
    # A margin is None when too few rivals came back to say what would
    # displace the expected agent, and folding those into the denominator
    # turned "we could not tell" into "every guard has room" — under
    # `--limit 3` that all-clear covered nothing at all.
    measured = [g for g in guards if g["margin"] is not None]
    unmeasured = len(guards) - len(measured)
    at_risk = [g for g in measured if 0 <= g["margin"] < thin_margin]

    # Silence would read as a steady week, which is the same information loss
    # the limit guard exists to prevent, only quieter. Both reasons for having
    # nothing to say get said: this checked only the depth mismatch, and a
    # --category run — which zeroes `moves` while leaving `previous` set —
    # printed no section at all. A guard that checks one side is half a guard.
    if not moves and history and (previous is None or partial):
        out.append("## Moved since the last run")
        out.append("")
        if partial:
            out.append("*Not compared: this run measured one category, and a "
                       "recorded run covers all of them.*")
        else:
            depths = sorted({run.get("limit", DEFAULT_LIMIT) for run in history})
            out.append(f"*Nothing to compare against: this run measured to "
                       f"{limit}, and the {len(history)} recorded "
                       f"{'run' if len(history) == 1 else 'runs'} used "
                       f"{', '.join(str(d) for d in depths)}. Scores are not "
                       f"comparable across depths.*")
        out.append("")

    if moves:
        out.append("## Moved since the last run")
        out.append("")
        if previous:
            out.append(f"Against `{previous.get('commit') or '?'}` "
                       f"({previous.get('at', '?')}), which held "
                       f"{previous.get('agents', '?')} agents.")
            out.append("")
        out.append("| Category | Was | Now | Change |")
        out.append("| --- | ---: | ---: | ---: |")
        for move in moves:
            out.append(f"| {move['category']} | {move['from']:.3f} "
                       f"| {move['to']:.3f} | {move['delta']:+.3f} |")
        out.append("")

    out.append("## Guards")
    out.append("")
    if failing:
        out.append(f"**{len(failing)} failing now:**")
        for guard in failing:
            out.append(f"- `{guard['query']}` — expected one of "
                       f"{', '.join(guard['expected'])}")
        out.append("")
    out.append(f"{len(at_risk)} of {len(measured)} measured guards pass by "
               f"less than {thin_margin}:")
    out.append("")
    if unmeasured:
        out.append(f"*{unmeasured} could not be measured — fewer than three "
                   f"other results came back, so nothing there could take the "
                   f"place. Raise `--limit` to measure them.*")
        out.append("")
    if at_risk:
        out.append("| Query | Rank | Margin | Next in line |")
        out.append("| --- | ---: | ---: | --- |")
        for guard in sorted(at_risk, key=lambda g: g["margin"]):
            out.append(f"| {guard['query']} | {guard['rank']} "
                       f"| {guard['margin']:+.4f} | {guard['rival']} |")
    elif measured:
        out.append("None of the measured guards is close.")
    return "\n".join(out) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(prog="quality.py",
                                     description=__doc__.split("\n")[0])
    parser.add_argument("--category", help="only measure agents in this category")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT,
                        help="how deep to look for each agent (default: 10)")
    parser.add_argument("--worst", type=int, default=15,
                        help="how many weak entries to list (default: 15)")
    parser.add_argument("--thin-margin", type=float, default=THIN_MARGIN,
                        help=f"report guards passing by less (default: {THIN_MARGIN})")
    parser.add_argument("--record", action="store_true",
                        help="append this run to the recorded history")
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

    # Read before recording, or the run being reported becomes its own
    # baseline and every category looks unchanged.
    history = read_history()
    previous = comparable(history, args.limit)
    # Only meaningful over the whole catalogue: --category measures a subset,
    # and comparing that against a full run would report the difference
    # between two questions as a change over time.
    if args.category:
        # A single-category run is not comparable with a whole-catalogue one,
        # so there is no baseline — not an empty list of moves beside a
        # baseline commit, which reads as "nothing moved since then". The
        # markdown says so in words; --json must not imply the opposite.
        moves, previous = [], None
    else:
        moves = movement(categories, previous, limit=args.limit)

    if args.record:
        if args.category:
            print("Refusing to record a partial run; drop --category.",
                  file=sys.stderr)
            return 1
        written = record(categories, guards, len(agents), args.limit)
        print(f"Recorded {written['commit'] or 'this run'} to "
              f"{quality_data.path()}", file=sys.stderr)

    if args.as_json:
        report = json.dumps({"categories": categories, "agents": rows,
                             "guards": guards, "limit": args.limit,
                             "moved": moves,
                             "compared_against": (previous or {}).get("commit")},
                            indent=2)
    else:
        report = render(categories, weakest, guards, args.thin_margin,
                        moves=moves, previous=previous, limit=args.limit,
                        history=history, partial=bool(args.category))

    if args.out:
        with open(args.out, "w") as f:
            f.write(report if report.endswith("\n") else report + "\n")
        print(f"Wrote {args.out}", file=sys.stderr)
    else:
        print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
