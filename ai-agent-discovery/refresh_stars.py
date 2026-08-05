"""Refresh GitHub star counts in data/agents.json.

    python refresh_stars.py --dry-run     # show what would change
    python refresh_stars.py               # write the updates

Star counts in the catalogue are hand-entered and go stale. This re-reads them
from the GitHub API for every agent whose URL points at a repository; agents
hosted elsewhere are left alone.

Unauthenticated requests are limited to 60/hour. Set GITHUB_TOKEN to raise
that to 5000/hour.
"""

import argparse
import json
import logging
import os
import re
import sys
import urllib.error
import urllib.request

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), 'backend')))

import config  # noqa: E402
from logging_setup import configure  # noqa: E402

logger = logging.getLogger("refresh_stars")

API_ROOT = "https://api.github.com/repos/"
REPO_URL = re.compile(r"^https?://(?:www\.)?github\.com/([^/]+)/([^/#?]+)", re.IGNORECASE)


def parse_repo(url):
    """Return "owner/name" for a GitHub repository URL, else None.

    Only real repository URLs qualify; github.com/features/copilot and
    non-GitHub homepages return None.
    """
    if not url:
        return None
    match = REPO_URL.match(url.strip())
    if not match:
        return None
    owner, name = match.group(1), match.group(2)
    if owner.lower() in {"features", "about", "marketplace", "orgs", "sponsors", "settings"}:
        return None
    return f"{owner}/{name.removesuffix('.git')}"


def fetch_stars(repo, token=None, timeout=10):
    """Return the stargazer count for "owner/name", or None if unavailable."""
    request = urllib.request.Request(
        API_ROOT + repo,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "ai-agent-discovery-refresh-stars",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response).get("stargazers_count")
    except urllib.error.HTTPError as e:
        if e.code == 403 and "rate limit" in str(e.headers.get("x-ratelimit-remaining", "")):
            logger.error("GitHub rate limit reached; set GITHUB_TOKEN to raise it.")
        elif e.code == 404:
            logger.warning("%s: repository not found", repo)
        else:
            logger.warning("%s: HTTP %s", repo, e.code)
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as e:
        logger.warning("%s: %s", repo, e)
    return None


def plan_updates(records, lookup):
    """Work out which records need a new star count.

    `lookup` maps "owner/name" to a count (or None). Returns a list of
    (record, old, new) for entries whose count actually changed.
    """
    changes = []
    for record in records:
        repo = parse_repo(record.get("url"))
        if repo is None:
            continue
        new = lookup.get(repo)
        if new is None:
            continue
        old = record.get("github_stars") or 0
        if int(new) != int(old):
            changes.append((record, int(old), int(new)))
    return changes


def format_change(record, old, new):
    arrow = "↑" if new > old else "↓"
    return f"  {record.get('name', '?'):<20} {old:>8,} {arrow} {new:>8,}"


def main(argv=None):
    parser = argparse.ArgumentParser(prog="refresh_stars.py", description=__doc__.split("\n")[0])
    parser.add_argument("--dry-run", action="store_true", help="report changes without writing")
    parser.add_argument("--token", default=os.getenv("GITHUB_TOKEN"), help="GitHub token (or set GITHUB_TOKEN)")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    configure("DEBUG" if args.verbose else "INFO")

    if not os.path.exists(config.AGENTS_JSON):
        logger.error("%s not found", config.AGENTS_JSON)
        return 1

    with open(config.AGENTS_JSON) as f:
        records = json.load(f)

    repos = {parse_repo(r.get("url")) for r in records}
    repos.discard(None)
    logger.info("Checking %d GitHub repositories (of %d agents)...", len(repos), len(records))

    lookup = {repo: fetch_stars(repo, args.token) for repo in sorted(repos)}
    failed = [repo for repo, stars in lookup.items() if stars is None]

    if failed:
        logger.warning("Could not fetch %d of %d repo(s): %s", len(failed), len(repos), ", ".join(failed))

    # "Nothing changed" and "nothing could be checked" are very different
    # outcomes; do not report the second as if it were the first.
    if failed and len(failed) == len(repos):
        logger.error("No repositories could be checked. Star counts are unverified.")
        return 1

    changes = plan_updates(records, lookup)
    if not changes:
        logger.info("All checked star counts are already up to date.")
    else:
        print(f"{len(changes)} star count(s) changed:")
        for change in changes:
            print(format_change(*change))

    if args.dry_run:
        logger.info("Dry run: %s left unchanged.", config.AGENTS_JSON)
        return 0

    if changes:
        for record, _, new in changes:
            record["github_stars"] = new
        with open(config.AGENTS_JSON, "w") as f:
            json.dump(records, f, indent=2)
        logger.info("Wrote %s. Re-run seed.py to reindex.", config.AGENTS_JSON)

    return 0


if __name__ == "__main__":
    sys.exit(main())
