"""Summarise a week of catalogue activity as one report.

    python digest.py                              # last 7 days, as markdown
    python digest.py --days 30
    python digest.py --audit audit.json           # fold in health findings

Three scheduled jobs each produced their own output: star counts, health
statuses, link checks, discovery candidates. Four step summaries and two
issues a week is four places to look and two to ignore.

This reads what those jobs already wrote — `data/changelog.json` for what
changed, and optionally the JSON from `audit.py` for what still needs a
person — and turns it into one thing worth reading. It makes no network
calls of its own, so it costs no API budget and can be tested offline.
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), 'backend')))

import changelog_data  # noqa: E402
from logging_setup import configure  # noqa: E402

logger = logging.getLogger("digest")

# Findings a maintainer has to decide about, as opposed to ones the audit
# already acted on by writing a status.
NEEDS_A_PERSON = ("missing", "moved", "stack")

# Archived entries with nowhere to send a reader. Not an audit "finding" —
# GitHub has nothing to say about it — but the one curation gap the automated
# pass can identify and cannot close, so it belongs in the same report.
NO_ALTERNATIVE = "no alternative"

# Names to spell out before falling back to a count. A busy week added 115
# agents; a digest that lists all of them is the thing it was meant to
# replace.
MAX_NAMED = 12


def _parsed(timestamp):
    """A timezone-aware datetime, or None if it cannot be read."""
    if not isinstance(timestamp, str) or not timestamp.strip():
        return None
    try:
        when = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)


def recent(entries, days):
    """Changelog entries from the last `days`.

    An entry with an unreadable date is kept rather than dropped: losing a
    real change is worse than including an old one, and the date is only
    used to decide the window.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    kept = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        when = _parsed(entry.get("at"))
        if when is None or when >= cutoff:
            kept.append(entry)
    return kept


def summarise_changes(entries):
    """Totals across a window, deduplicated by agent.

    An agent added and then edited twice is one addition, not three events —
    the question is what changed about the catalogue, not how many commits
    it took.
    """
    added, removed, edited = set(), set(), set()
    for entry in entries:
        added |= set(changelog_data.names(entry.get("added")))
        removed |= set(changelog_data.names(entry.get("removed")))
        edited |= set(changelog_data.names(entry.get("edited"), key="name"))

    # Something added and removed in the same window nets out; reporting it
    # as both is two pieces of news about a thing that is not there.
    both = added & removed
    return {
        "added": sorted(added - both),
        "removed": sorted(removed - both),
        "edited": sorted(edited - added - removed),
    }


def summarise_findings(findings):
    """Audit findings grouped by kind, keeping only what needs a decision."""
    grouped = {}
    for finding in findings or []:
        if not isinstance(finding, dict):
            continue
        for issue in finding.get("issues") or []:
            if not isinstance(issue, dict):
                continue
            kind = issue.get("kind")
            if kind in NEEDS_A_PERSON:
                grouped.setdefault(kind, []).append(
                    (finding.get("name", "?"), issue.get("detail", "")))
    return {kind: sorted(items) for kind, items in grouped.items()}


def _listed(names):
    """Names as a sentence, abbreviated past MAX_NAMED."""
    if len(names) <= MAX_NAMED:
        return ", ".join(names)
    return f"{', '.join(names[:MAX_NAMED])} and {len(names) - MAX_NAMED} more"


def summarise_candidates(candidates):
    """Crawler proposals worth a look, best-starred first.

    Passed through rather than filtered: discover.py has already refused the
    reading lists and the configuration collections, so what arrives here is
    a shortlist somebody should actually skim.
    """
    rows = []
    for candidate in candidates or []:
        if not isinstance(candidate, dict) or not candidate.get("name"):
            continue
        stars = candidate.get("github_stars")
        rows.append((candidate["name"], candidate.get("category") or "?",
                     stars if isinstance(stars, int) else 0,
                     candidate.get("url") or ""))
    return sorted(rows, key=lambda row: -row[2])


def render(changes, findings, days, total=None, candidates=None,
           audit_incomplete=False):
    """The digest as markdown."""
    lines = [f"## Catalogue activity, last {days} days", ""]

    if total is not None:
        lines += [f"The catalogue holds **{total}** agents.", ""]

    if any(changes.values()):
        for label, key in [("Added", "added"), ("Removed", "removed"), ("Edited", "edited")]:
            names = changes[key]
            if names:
                lines.append(f"**{label} ({len(names)})** — {_listed(names)}")
                lines.append("")
    else:
        lines += ["Nothing changed.", ""]

    # One heading, written once. The warning and the findings are not
    # alternatives — audit.py prints its findings and *then* returns 1 when a
    # repository was skipped, so an incomplete run carrying real findings is
    # the common case, and it printed the heading twice. Unconditional rather
    # than repeated in two exhaustive branches, which is the same invariant
    # stated in two places that can drift.
    lines += ["### Needs a decision", ""]

    if audit_incomplete:
        lines += ["⚠️ **The audit did not complete**, so this is not a clean "
                  "bill of health — anything it would have flagged is missing "
                  "from this report. See the job log.", ""]

    if findings:
        for kind in NEEDS_A_PERSON:
            items = findings.get(kind)
            if not items:
                continue
            lines.append(f"**{kind}** ({len(items)})")
            lines += [f"- `{name}` — {detail}" for name, detail in items[:MAX_NAMED]]
            if len(items) > MAX_NAMED:
                lines.append(f"- …and {len(items) - MAX_NAMED} more")
            lines.append("")
    elif not audit_incomplete:
        # The wording differs from the warning above on purpose: the workflow
        # greps for "Nothing outstanding" to decide a week was quiet, so a
        # broken audit must not produce that phrase or the failure suppresses
        # its own report.
        lines += ["Nothing outstanding.", ""]

    if candidates:
        lines += ["### Could be added", "",
                  "| Agent | Category | Stars | Link |", "| --- | --- | --- | --- |"]
        lines += [f"| {name} | {category} | {stars:,} | {url} |"
                  for name, category, stars, url in candidates[:MAX_NAMED]]
        if len(candidates) > MAX_NAMED:
            lines.append(f"| …and {len(candidates) - MAX_NAMED} more | | | |")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(prog="digest.py", description=__doc__.split("\n")[0])
    parser.add_argument("--days", type=int, default=7, help="window in days (default: 7)")
    parser.add_argument("--audit", default=None,
                        help="JSON from audit.py --json, to include what needs a person")
    parser.add_argument("--audit-incomplete", action="store_true",
                        help="say the audit could not be trusted, rather than "
                             "reporting silence as nothing outstanding")
    parser.add_argument("--candidates", default=None,
                        help="JSON from discover.py --json, to include what could be added")
    parser.add_argument("--out", default=None, help="write here instead of stdout")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    configure("DEBUG" if args.verbose else "INFO")

    if args.days < 1:
        logger.error("--days must be at least 1.")
        return 1

    # "No file" and "a file with nothing in it" are different: the first is a
    # setup mistake worth failing on, the second is a truthful quiet week.
    # Collapsing them made a valid empty history fail the weekly job.
    if not changelog_data.path().exists():
        logger.error("No changelog to summarise. Run changelog.py first.")
        return 1

    entries = changelog_data.read()

    findings = []
    if args.audit:
        try:
            with open(args.audit) as f:
                findings = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            # A missing audit is a smaller problem than no digest at all.
            logger.warning("Could not read %s (%s); reporting changes only.", args.audit, e)

    candidates = []
    if args.candidates:
        try:
            with open(args.candidates) as f:
                candidates = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("Could not read %s (%s); reporting without candidates.",
                           args.candidates, e)

    window = recent(entries, args.days)
    total = next((e.get("total") for e in window if isinstance(e.get("total"), int)), None)
    text = render(summarise_changes(window), summarise_findings(findings), args.days,
                  total, summarise_candidates(candidates),
                  audit_incomplete=args.audit_incomplete)

    if args.out:
        with open(args.out, "w") as f:
            f.write(text)
        logger.info("Wrote the digest to %s", args.out)
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
