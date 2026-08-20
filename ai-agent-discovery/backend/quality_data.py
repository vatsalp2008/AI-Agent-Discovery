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

# Enough to show a trend without turning the page into a spreadsheet. The
# oldest runs matter least: what a maintainer wants is "is this getting
# worse", which the recent ones answer.
MAX_RUNS = 20


def path():
    """Where the recorded runs live."""
    return config.DATA_DIR / "quality-history.jsonl"


def read(limit=MAX_RUNS):
    """Recorded runs, newest first.

    A damaged line is skipped rather than fatal. This is a record of
    measurements taken over months, and one bad append should not cost the
    rest of it — the same call the CLI's own reader makes.
    """
    where = path()
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

    runs.reverse()
    return runs[:limit] if limit else runs


def latest():
    """The most recent run, or None."""
    runs = read(limit=1)
    return runs[0] if runs else None


def movement(runs):
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

    before = earlier.get("categories") or {}
    moves = []
    for category, score in (newest.get("categories") or {}).items():
        was = before.get(category)
        if not isinstance(was, (int, float)) or not isinstance(score, (int, float)):
            continue
        if was != score:
            moves.append({"category": category, "from": was, "to": score,
                          "delta": round(score - was, 3)})
    return sorted(moves, key=lambda move: move["delta"])
