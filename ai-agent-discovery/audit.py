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

from discover import LANGUAGE_NAMES, NOT_A_TECH_STACK  # noqa: E402
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
    return {tech.casefold() for tech in record.get("tech_stack") or []}


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
        issues.append({"kind": "moved",
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
        if named.casefold() not in _recorded_stack(record):
            issues.append({"kind": "stack",
                           "detail": f"mostly {named}, which the entry does not list"})

    return issues


def audit(records, token=None, stale_months=DEFAULT_STALE_MONTHS, on_progress=None):
    """Check every entry with a GitHub URL. Returns (findings, skipped)."""
    findings = []
    skipped = []

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

        issues = find_issues(record, data, stale_months=stale_months)
        if issues:
            findings.append({"name": record.get("name"), "url": record.get("url"),
                             "issues": issues})
        if on_progress:
            on_progress(record)

    return findings, skipped


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
    parser.add_argument("--token", default=os.getenv("GITHUB_TOKEN"),
                        help="GitHub token (or set GITHUB_TOKEN)")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    configure("DEBUG" if args.verbose else "INFO")

    if not os.path.exists(config.AGENTS_JSON):
        logger.error("%s not found", config.AGENTS_JSON)
        return 1

    with open(config.AGENTS_JSON) as f:
        records = json.load(f)

    checkable = [r for r in records if parse_repo(r.get("url"))]
    logger.info("Auditing %d GitHub repositories (of %d agents)...",
                len(checkable), len(records))

    findings, skipped = audit(records, token=args.token, stale_months=args.stale_months)

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

    return 1 if (findings and args.fail_on_findings) else 0


if __name__ == "__main__":
    sys.exit(main())
