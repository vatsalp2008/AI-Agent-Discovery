"""Build a change history for the catalogue from git.

    python changelog.py              # write data/changelog.json
    python changelog.py --dry-run    # show what it would contain
    python changelog.py --since 2026-08-01

`data/agents.json` is version controlled, so its history already exists — this
turns it into something the app can serve. Every commit that touched the file
becomes an entry saying which agents arrived, which left, and which were
edited.

Generated rather than served live: shelling out to git on every request would
tie the web process to a working tree it may not have (a container ships the
JSON, not the repository), and the history only changes when the catalogue
does.
"""

import argparse
import json
import logging
import os
import subprocess
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), 'backend')))

import config  # noqa: E402
from logging_setup import configure  # noqa: E402

logger = logging.getLogger("changelog")

# Fields worth reporting a change in. Star counts move constantly and are
# refreshed weekly by a bot; including them would make every entry a wall of
# numbers and bury the additions.
TRACKED_FIELDS = ("description", "category", "tech_stack", "url", "use_case", "status")

# What an absent field means. Without this, the commit that introduced
# `status` read as 204 agents edited, and the commit that stopped writing the
# default read as 204 more — a formatting round-trip burying the real news
# either side of it.
FIELD_DEFAULTS = {"status": "active", "use_case": "", "url": "", "tech_stack": []}


def _value(record, field):
    """A field's value, with an absent one read as its default."""
    if field in record and record[field] is not None:
        return record[field]
    return FIELD_DEFAULTS.get(field)


def _git(args, cwd):
    """Run git, returning stdout, or None if it failed."""
    try:
        result = subprocess.run(["git", *args], cwd=cwd, capture_output=True,
                                text=True, check=True)
        return result.stdout
    except (subprocess.CalledProcessError, FileNotFoundError, OSError) as e:
        logger.debug("git %s failed: %s", " ".join(args), e)
        return None


def revisions(path, repo_root, since=None):
    """Commits that touched `path`, oldest first.

    Oldest first so the diffs read forwards; git reports newest first.
    """
    args = ["log", "--format=%H%x1f%aI%x1f%s", "--follow"]
    if since:
        args.append(f"--since={since}")
    args += ["--", path]

    out = _git(args, repo_root)
    if not out:
        return []

    entries = []
    for line in out.strip().splitlines():
        parts = line.split("\x1f")
        if len(parts) == 3:
            entries.append({"commit": parts[0], "at": parts[1], "subject": parts[2]})
    entries.reverse()
    return entries


def catalogue_at(commit, path, repo_root):
    """The catalogue as of `commit`, or None if it cannot be read."""
    out = _git(["show", f"{commit}:{path}"], repo_root)
    if out is None:
        return None
    try:
        records = json.loads(out)
    except json.JSONDecodeError:
        return None
    return records if isinstance(records, list) else None


def _by_name(records):
    return {r["name"]: r for r in records if isinstance(r, dict) and r.get("name")}


def compare(before, after):
    """What changed between two catalogue snapshots.

    Edits are reported per field rather than as "changed", so the feed says
    *what* moved — a re-categorisation and a rewritten description are not
    the same news.
    """
    old, new = _by_name(before or []), _by_name(after or [])

    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))

    edited = []
    for name in sorted(set(old) & set(new)):
        fields = [
            {"field": field, "from": _value(old[name], field), "to": _value(new[name], field)}
            for field in TRACKED_FIELDS
            if _value(old[name], field) != _value(new[name], field)
        ]
        if fields:
            edited.append({"name": name, "fields": fields})

    return {"added": added, "removed": removed, "edited": edited}


def build(repo_root=None, path="data/agents.json", since=None):
    """The change history, newest first."""
    repo_root = repo_root or config.REPO_ROOT

    history = revisions(path, repo_root, since=since)
    if not history:
        return []

    entries = []
    previous = None
    for revision in history:
        snapshot = catalogue_at(revision["commit"], path, repo_root)
        if snapshot is None:
            # A commit whose version cannot be read would otherwise look like
            # the catalogue was emptied and refilled.
            logger.warning("Skipping %s: could not read the catalogue there",
                           revision["commit"][:8])
            continue

        # The first readable revision has nothing to compare against; report
        # it as the starting point rather than as N agents "added" today.
        is_baseline = previous is None
        changes = {"added": [], "removed": [], "edited": []} if is_baseline \
            else compare(previous, snapshot)
        previous = snapshot

        # `previous is None` rather than a loop index: if an earlier revision
        # was unreadable, the first one that *parses* is the baseline, and
        # dropping it would lose the starting point entirely.
        if is_baseline is False and not any(changes.values()):
            continue   # touched the file without changing any tracked field

        entries.append({
            "commit": revision["commit"][:8],
            "at": revision["at"],
            "subject": revision["subject"],
            "total": len(snapshot),
            **changes,
        })

    # Which names the catalogue still has. An entry that added an agent
    # removed three commits later would otherwise link to a page that 404s —
    # "Windsurf" did exactly that after it was renamed to Devin Desktop.
    current = set(_by_name(previous or []))
    for entry in entries:
        entry["gone"] = sorted(
            {name for name in entry["added"] + entry["removed"] if name not in current})

    entries.reverse()
    return entries


def summarise(entry):
    bits = []
    if entry["added"]:
        bits.append(f"+{len(entry['added'])}")
    if entry["removed"]:
        bits.append(f"-{len(entry['removed'])}")
    if entry["edited"]:
        bits.append(f"~{len(entry['edited'])}")
    return ", ".join(bits) or "no change"


def main(argv=None):
    parser = argparse.ArgumentParser(prog="changelog.py", description=__doc__.split("\n")[0])
    parser.add_argument("--since", default=None, help="only commits after this date")
    parser.add_argument("--dry-run", action="store_true", help="print instead of writing")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    configure("DEBUG" if args.verbose else "INFO")

    entries = build(since=args.since)
    if not entries:
        # No history is not the same as an empty history: outside a git
        # checkout there is nothing to build from, and writing [] would
        # replace a good file with an empty one.
        logger.error("No history found. Is this a git checkout with data/agents.json?")
        return 1

    if args.dry_run:
        for entry in entries:
            print(f"  {entry['at'][:10]}  {entry['commit']}  {summarise(entry):<12} "
                  f"{entry['subject']}")
        return 0

    path = config.DATA_DIR / "changelog.json"
    os.makedirs(path.parent, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    with open(tmp, "w") as f:
        json.dump(entries, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)

    logger.info("Wrote %d entries to %s", len(entries), path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
