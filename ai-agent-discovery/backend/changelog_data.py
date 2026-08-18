"""Reading the generated change history.

`changelog.py` writes `data/changelog.json`; the API serves it and the digest
summarises it. Both had their own copy of "read names out of a list that might
hold anything", which is one drift away from the two disagreeing about what a
damaged file means.

It lives in `backend/` rather than beside the writer so the API can import it
without depending on a top-level script, and it deliberately pulls in nothing
beyond `config` — the digest is a CLI and should not load Flask to read a
file.
"""

import json
import logging

import config

logger = logging.getLogger(__name__)


def read():
    """The history, or [] when there is none to read.

    Absent is the normal state before the generator has ever run, and an
    empty history is a truthful answer to "what changed" — not an error.
    Entries that are not objects are dropped: a list that parses can still
    hold anything, and every caller reads fields off each entry.
    """
    path = config.DATA_DIR / "changelog.json"
    try:
        with open(path) as f:
            entries = json.load(f)
    except (OSError, json.JSONDecodeError):
        logger.info("No changelog at %s; run changelog.py to build one.", path)
        return []

    if not isinstance(entries, list):
        return []
    return [entry for entry in entries if isinstance(entry, dict)]


def names(value, key=None):
    """String names out of a changelog list, whatever it actually holds.

    A bare string where an object belongs is salvaged rather than dropped:
    `edited: ["Cursor"]` most likely means Cursor was edited, and losing a
    real change to save a shape check is the worse trade.
    """
    if not isinstance(value, list):
        return []

    found = []
    for item in value:
        if key and isinstance(item, dict):
            item = item.get(key)
        if isinstance(item, str) and item.strip():
            found.append(item)
    return found
