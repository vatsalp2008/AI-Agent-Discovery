"""Reading the recorded retrieval-quality runs.

Its own module for the same reason as changelog_data: quality.py imports the
vector store and the embedding client, and the web process has no business
paying for either to read a small JSON-lines file. The measuring tool writes
this; everything else only ever reads it.

One run per line, appended by `make quality-record`. The file is committed, so
a container that ships the data directory has the history without needing a
working tree or a model.
"""

import json
import logging

import config

logger = logging.getLogger(__name__)

# How deep a run looks for each agent. Defined here rather than in quality.py
# so the reader and the writer cannot drift: a run recorded before the field
# existed was taken at this depth, and reading it as "unknown" instead is what
# made the trend on /changes come out empty the first time it was wired up.
DEFAULT_LIMIT = 10

# How far a category has to move before it is worth mentioning. Scores wobble
# by a thousandth or two between runs on identical data, and the published
# panel is where that noise would be most visible. Defined here so the page
# and `make quality` cannot answer "what moved" differently.
NOTABLE_MOVE = 0.02

# Enough to show a trend without turning the page into a spreadsheet. The
# oldest runs matter least: what a maintainer wants is "is this getting
# worse", which the recent ones answer.
MAX_RUNS = 20


def path():
    """Where the recorded runs live."""
    return config.DATA_DIR / "quality-history.jsonl"


def read(limit=MAX_RUNS, where=None, newest_first=True):
    """Recorded runs.

    A damaged line is skipped rather than fatal. This is a record of
    measurements taken over months, and one bad append should not cost the
    rest of it — the same call the CLI's own reader makes.
    """
    where = where or path()
    try:
        text = where.read_text()
    except OSError:
        logger.info("No quality history at %s; run `make quality-record`.", where)
        return []

    runs = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            run = json.loads(line)
        except json.JSONDecodeError:
            logger.warning("Skipping an unreadable line in %s", where)
            continue
        if isinstance(run, dict) and isinstance(run.get("categories"), dict):
            runs.append(run)

    if limit is not None:
        # Sliced from the recent end whichever way they are ordered. Taken
        # before the reverse, `runs[:limit]` on an oldest-first read returned
        # the runs the cap exists to drop.
        runs = runs[-limit:] if limit else []
    if newest_first:
        runs.reverse()
    return runs


def read_with_total(limit=MAX_RUNS):
    """Recent runs and how many there are in all, from one pass.

    /api/quality wants both. Asking read() then total() parsed the whole file
    twice per request — and logged "no history" twice when it was absent —
    where /api/changelog derives its total from the single list it already
    holds.
    """
    runs = read(limit=None)
    return (runs[:limit] if limit is not None else runs), len(runs)


def moves_between(before, after, notable=NOTABLE_MOVE):
    """Categories that moved by at least `notable`, biggest fall first.

    The one implementation. It lived in two — here and in quality.py — with
    the float-rounding fix applied twice and a test whose only job was to
    catch the next divergence.

    Both directions are reported. A category climbing is usually somebody's
    wording fix working, and only ever hearing bad news hides that.
    """
    moves = []
    for category, score in (after or {}).items():
        was = (before or {}).get(category)
        if not isinstance(was, (int, float)) or not isinstance(score, (int, float)):
            continue
        # Rounded before comparing: scores are stored to three places, and
        # binary floats put 0.800 -> 0.820 at 0.0199999999999999, so exactly
        # the threshold was dropped for 40 of the 281 pairs in the range
        # these scores occupy — while 0.900 -> 0.880 came through.
        if round(abs(score - was), 3) >= notable:
            moves.append({"category": category, "from": was, "to": score,
                          "delta": round(score - was, 3)})
    return sorted(moves, key=lambda move: move["delta"])


def movement(runs, notable=NOTABLE_MOVE):
    """What changed between the two most recent comparable runs.

    Comparable means measured to the same depth: a run at `--limit 3` cannot
    see an agent ranked fourth, so every score is lower and the difference
    would be the setting rather than the catalogue.
    """
    if len(runs) < 2:
        return []

    newest = runs[0]
    depth = newest.get("limit", DEFAULT_LIMIT)
    earlier = next((run for run in runs[1:]
                    if run.get("limit", DEFAULT_LIMIT) == depth), None)
    if earlier is None:
        return []

    return moves_between(earlier.get("categories"),
                         newest.get("categories"), notable)
