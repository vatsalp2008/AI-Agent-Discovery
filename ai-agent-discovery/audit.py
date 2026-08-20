"""Find catalogue entries that have gone stale.

    python audit.py                 # report what needs attention
    python audit.py --json          # machine readable
    python audit.py --stale-months 24

`discover.py` finds agents the catalogue is missing. This is the other half:
entries that are already here and no longer describe reality. A curated
catalogue rots quietly — a project gets archived, an org renames, a repository
stops being touched — and none of it shows up until somebody clicks through.

It reports; it does not edit. The submission queue only accepts *new* agents
(it rejects anything whose name is already taken), so an update is a
maintainer's judgement call: an archived project might deserve removal, or a
note, or nothing at all if it is archived because it finished.

One API call per repository, so it wants GITHUB_TOKEN for a catalogue of this
size — the unauthenticated budget is 60/hour.
"""

import argparse
import json
import logging
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), 'backend')))

from discover import LANGUAGE_NAMES, NOT_A_TECH_STACK, canonical_tech  # noqa: E402
from refresh_stars import parse_repo  # noqa: E402

import config  # noqa: E402
from logging_setup import configure  # noqa: E402

logger = logging.getLogger("audit")

API_ROOT = "https://api.github.com/repos/"

# A project untouched for this long is worth a look. Deliberately generous:
# plenty of good software is finished rather than abandoned, so this is a
# prompt to check, not a verdict.
DEFAULT_STALE_MONTHS = 18

# Languages that describe how a repository is *written down* rather than what
# it is built with. GitHub reports whichever has the most bytes, so an ML
# project ships as "Jupyter Notebook" and a research repo as "TeX" — neither
# says anything a curated stack should have to list. Ten of the first
# eighteen stack findings were "mostly Jupyter" against entries that
# correctly said Python and PyTorch.
FORMAT_LANGUAGES = NOT_A_TECH_STACK | {"Jupyter Notebook", "Dockerfile", "CMake"}


class Unavailable(Exception):
    """A repository could not be read at all."""


def fetch_repo(repo, token=None, timeout=10):
    """Return the GitHub metadata for "owner/name"."""
    request = urllib.request.Request(
        API_ROOT + repo,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "ai-agent-discovery-audit",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None          # deleted or made private: a real finding
        if e.code in (403, 429):
            raise Unavailable("rate limited; set GITHUB_TOKEN to raise the budget") from e
        raise Unavailable(f"HTTP {e.code}") from e
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as e:
        raise Unavailable(str(e)) from e


def _months_since(timestamp):
    """Whole months between `timestamp` (ISO 8601) and now, or None."""
    if not isinstance(timestamp, str):
        return None
    try:
        when = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    return int((datetime.now(timezone.utc) - when) / timedelta(days=30))


def _recorded_stack(record):
    return {canonical_tech(tech) for tech in record.get("tech_stack") or []}


def find_issues(record, data, stale_months=DEFAULT_STALE_MONTHS):
    """Everything worth a maintainer's attention about one entry.

    `data` is the GitHub payload, or None when the repository is gone.
    Returns a list of {kind, detail} — several can be true at once, and a
    project that is both archived and renamed should say both.
    """
    if data is None:
        return [{"kind": "missing", "detail": "the repository no longer exists or is private"}]

    issues = []

    if data.get("archived"):
        issues.append({"kind": "archived", "detail": "the repository is archived on GitHub"})

    # The API answers on the old path after a rename, so this is the only
    # place the new name shows up without following a redirect.
    current = (data.get("full_name") or "").casefold()
    recorded = (parse_repo(record.get("url")) or "").casefold()
    if current and recorded and current != recorded:
        # `to` carried structurally: --follow-moves rewrites the URL from it,
        # and parsing the prose back out would be one wording change away
        # from silently doing nothing.
        issues.append({"kind": "moved", "to": data["full_name"],
                       "detail": f"now at {data['full_name']}, recorded as {recorded}"})

    months = _months_since(data.get("pushed_at"))
    if months is not None and months >= stale_months:
        issues.append({"kind": "dormant", "detail": f"no commits for {months} months"})

    # Only when the primary language is missing from the stack entirely. The
    # catalogue's stacks are curated and deliberately richer than one word,
    # so a partial match is not a problem.
    language = data.get("language")
    if language and language not in FORMAT_LANGUAGES:
        named = LANGUAGE_NAMES.get(language, language)
        if canonical_tech(named) not in _recorded_stack(record):
            issues.append({"kind": "stack",
                           "detail": f"mostly {named}, which the entry does not list"})

    return issues


def audit(records, token=None, stale_months=DEFAULT_STALE_MONTHS, on_progress=None):
    """Check every entry with a GitHub URL.

    Returns (findings, skipped, checked) — `checked` being the names actually
    examined, so a caller writing statuses back knows what it may touch.
    """
    findings = []
    skipped = []
    checked = set()

    for record in records:
        repo = parse_repo(record.get("url"))
        if repo is None:
            # Hosted somewhere else, or no URL. Not something to check here.
            continue

        try:
            data = fetch_repo(repo, token=token)
        except Unavailable as e:
            skipped.append((record.get("name"), str(e)))
            continue

        checked.add(record.get("name"))
        issues = find_issues(record, data, stale_months=stale_months)
        if issues:
            findings.append({"name": record.get("name"), "url": record.get("url"),
                             "issues": issues})
        if on_progress:
            on_progress(record)

    return findings, skipped, checked


# Only these translate into a status. "stack" and "moved" want a human to
# decide what the entry should say instead, and "missing" might mean the
# entry should go entirely — none of them is a flag to flip.
STATUS_FROM = {"archived": "archived", "dormant": "dormant"}


def statuses_for(findings, records=None):
    """The status each flagged entry should carry, by name.

    Archived beats dormant: an archived project is not merely quiet, and a
    repository that is both should say the stronger thing.

    A `missing` repository keeps whatever status it already had. Clearing it
    would quietly upgrade a deleted project to healthy, which is the wrong
    direction for the one finding that most needs a human.
    """
    existing = {r.get("name"): r.get("status", "active") for r in records or []}

    wanted = {}
    for finding in findings:
        kinds = {issue["kind"] for issue in finding["issues"]}
        if "missing" in kinds:
            wanted[finding["name"]] = existing.get(finding["name"], "active")
            continue
        for kind in ("archived", "dormant"):
            if kind in kinds:
                wanted[finding["name"]] = STATUS_FROM[kind]
                break
    return wanted


def apply_statuses(records, wanted, checked=None):
    """Set `status` from `wanted`, clearing it on entries that recovered.

    Returns the list of (name, before, after) that actually changed. A
    project can come back — archived repositories get unarchived — so an
    entry the audit no longer flags is reset rather than carrying a stale
    warning forever.

    `checked` names the entries the audit actually looked at. Anything else
    is left alone: an entry hosted outside GitHub is never examined, and one
    whose repository has been deleted is reported as `missing` rather than
    healthy — clearing either would remove a warning nobody re-verified.
    """
    changes = []
    for record in records:
        name = record.get("name")
        if checked is not None and name not in checked:
            continue

        before = record.get("status", "active")
        after = wanted.get(name, "active")
        if before == after:
            continue
        if after == "active":
            record.pop("status", None)
        else:
            record["status"] = after
        changes.append((record.get("name"), before, after))
    return changes


def follow_moves(records, findings, checked=None):
    """Rewrite the URL of every entry whose repository was renamed.

    Returns (name, before, after) for each change. Only the owner/name part
    is replaced, so a URL pointing at a subpath or a non-github host is left
    alone — the finding is about the repository, not about the whole link.
    """
    moves = {}
    for finding in findings:
        for issue in finding["issues"]:
            if issue["kind"] == "moved" and issue.get("to"):
                moves[finding["name"]] = issue["to"]

    changes = []
    for record in records:
        name = record.get("name")
        if name not in moves or (checked is not None and name not in checked):
            continue

        old = record.get("url") or ""
        repo = parse_repo(old)
        if not repo:
            continue

        new = old.replace(repo, moves[name], 1)
        if new != old:
            record["url"] = new
            changes.append((name, old, new))
    return changes


def _write_catalogue(records):
    """tmp + replace, like admin.save_catalogue and changelog.main: an
    interrupted CI step must not leave a truncated catalogue."""
    tmp = f"{config.AGENTS_JSON}.tmp"
    with open(tmp, "w") as f:
        json.dump(records, f, indent=2)
        f.write("\n")
    os.replace(tmp, config.AGENTS_JSON)


def format_finding(finding):
    lines = [f"  {finding['name']:<24} {finding['url']}"]
    lines += [f"      {issue['kind']}: {issue['detail']}" for issue in finding["issues"]]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="audit.py", description=__doc__.split("\n")[0])
    parser.add_argument("--stale-months", type=int, default=DEFAULT_STALE_MONTHS,
                        help=f"flag projects untouched this long (default: {DEFAULT_STALE_MONTHS})")
    parser.add_argument("--json", action="store_true", dest="as_json",
                        help="print findings as JSON")
    parser.add_argument("--fail-on-findings", action="store_true",
                        help="exit non-zero when anything needs attention")
    parser.add_argument("--apply-status", action="store_true",
                        help="write archived/dormant back into the catalogue")
    parser.add_argument("--follow-moves", action="store_true",
                        help="rewrite URLs for repositories that were renamed")
    parser.add_argument("--token", default=os.getenv("GITHUB_TOKEN"),
                        help="GitHub token (or set GITHUB_TOKEN)")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    configure("DEBUG" if args.verbose else "INFO")

    # With --json, stdout is the data and nothing else may go there: the
    # write-back messages used to land after the JSON array and made the file
    # unparsable for anything reading it.
    def say(text):
        if args.as_json:
            logger.info("%s", text.strip())
        else:
            print(text)

    if not os.path.exists(config.AGENTS_JSON):
        logger.error("%s not found", config.AGENTS_JSON)
        return 1

    with open(config.AGENTS_JSON) as f:
        records = json.load(f)

    checkable = [r for r in records if parse_repo(r.get("url"))]
    logger.info("Auditing %d GitHub repositories (of %d agents)...",
                len(checkable), len(records))

    findings, skipped, checked = audit(records, token=args.token,
                                       stale_months=args.stale_months)

    # "Nothing is stale" and "nothing could be checked" are opposite
    # outcomes; the second must not read as a clean bill of health.
    if skipped and len(skipped) == len(checkable):
        logger.error("No repositories could be checked. The catalogue is unverified.")
        for name, reason in skipped[:3]:
            logger.error("  %s: %s", name, reason)
        return 1

    if args.as_json:
        print(json.dumps(findings, indent=2))
    else:
        if findings:
            print(f"\n{len(findings)} entr{'y' if len(findings) == 1 else 'ies'} need attention:\n")
            for finding in findings:
                print(format_finding(finding))
        else:
            print(f"\nAll {len(checkable)} entries look current.")

    if skipped:
        logger.warning("Could not check %d of %d: %s", len(skipped), len(checkable),
                       ", ".join(name for name, _ in skipped[:5]))

    if args.follow_moves:
        if skipped:
            logger.error("Refusing to rewrite URLs: %d entr(y|ies) could not be checked.",
                         len(skipped))
            return 1

        moved = follow_moves(records, findings, checked=checked)
        if moved:
            _write_catalogue(records)
            say(f"\nFollowed {len(moved)} rename(s):")
            for name, before, after in moved:
                say(f"  {name:<24} {before}\n  {'':<24} -> {after}")
        else:
            say("\nNo renames to follow.")

    if args.apply_status:
        if skipped:
            # An entry that could not be checked would look "not flagged" and
            # get its status cleared, quietly removing a real warning.
            logger.error("Refusing to write statuses: %d entr(y|ies) could not be "
                         "checked, and clearing their status would lose a warning.",
                         len(skipped))
            return 1

        changes = apply_statuses(records, statuses_for(findings, records), checked=checked)
        if changes:
            _write_catalogue(records)
            say(f"\nUpdated {len(changes)} entr{'y' if len(changes) == 1 else 'ies'}:")
            for name, before, after in changes:
                say(f"  {name:<24} {before} -> {after}")
        else:
            say("\nNo status changes.")

    return 1 if (findings and args.fail_on_findings) else 0


if __name__ == "__main__":
    sys.exit(main())
