"""Check that every URL in the catalogue still resolves.

    python ai-agent-discovery/check_links.py
    python ai-agent-discovery/check_links.py --json
    python ai-agent-discovery/check_links.py --fail-on-broken   # for CI

Projects get renamed, archived and deleted. A dead link in the catalogue is
invisible until somebody clicks it, so this walks every entry and reports what
no longer resolves.

Redirects are reported rather than treated as failures: GitHub redirects a
renamed repository, which is worth knowing about (the entry could be updated)
but is not broken.
"""

import argparse
import concurrent.futures
import json
import os
import sys
import urllib.error
import urllib.request

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), 'backend')))

import config  # noqa: E402
from logging_setup import configure  # noqa: E402

OK, REDIRECT, BROKEN, SKIPPED = "ok", "redirect", "broken", "skipped"

# The host refused to answer rather than saying the page is gone. Reported,
# but not as broken: devin.ai returns 429 to any automated request, and
# failing the weekly job on somebody else's bot protection is a false alarm
# every week for a page that is perfectly fine in a browser.
THROTTLED = "throttled"

# Some hosts refuse requests without a browser-ish agent.
USER_AGENT = "ai-agent-discovery-link-check"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Capture redirects instead of following them."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise _Redirected(newurl)


class _Redirected(Exception):
    def __init__(self, location):
        super().__init__(location)
        self.location = location


def check_url(url, timeout=10):
    """Return (status, detail) for one URL."""
    if not url:
        return SKIPPED, "no url"
    if not url.startswith(("http://", "https://")):
        return BROKEN, f"not an http(s) url: {url}"

    opener = urllib.request.build_opener(_NoRedirect)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT}, method="HEAD")

    try:
        with opener.open(request, timeout=timeout) as response:
            return OK, f"{response.status}"
    except _Redirected as e:
        return REDIRECT, f"-> {e.location}"
    except urllib.error.HTTPError as e:
        # HEAD is not universally supported; a 4xx may just mean that.
        if e.code == 429:
            return THROTTLED, "HTTP 429 (rate limited, not necessarily broken)"
        if e.code in (403, 405, 501):
            try:
                request.method = "GET"
                with opener.open(request, timeout=timeout) as response:
                    return OK, f"{response.status} (GET)"
            except _Redirected as redirect:
                return REDIRECT, f"-> {redirect.location}"
            except urllib.error.HTTPError as inner:
                # The retry can be throttled too: a host that refuses HEAD
                # with 403 and then rate-limits the GET is still refusing to
                # answer, not reporting a dead page.
                if inner.code == 429:
                    return THROTTLED, "HTTP 429 on GET (rate limited, not necessarily broken)"
                return BROKEN, f"{e.code}, and GET failed: HTTP {inner.code}"
            except Exception as inner:
                return BROKEN, f"{e.code}, and GET failed: {inner}"
        return BROKEN, f"HTTP {e.code}"
    except Exception as e:
        return BROKEN, str(e)


def check_catalogue(records, workers=8, timeout=10):
    """Check every record's URL, in parallel — this is all network wait."""
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(check_url, record.get("url", ""), timeout): record
            for record in records
        }
        for future in concurrent.futures.as_completed(futures):
            record = futures[future]
            status, detail = future.result()
            results.append({
                "name": record.get("name"),
                "url": record.get("url", ""),
                "status": status,
                "detail": detail,
            })

    results.sort(key=lambda r: (r["status"] != BROKEN, r["status"] != THROTTLED,
                                r["status"] != REDIRECT, r["name"] or ""))
    return results


def render(results):
    """Format the report.

    Names come from a hand-edited catalogue, so one may be missing entirely;
    a format spec on None raises and would discard every other result.
    """
    def label(result):
        return result.get("name") or "(unnamed)"

    broken = [r for r in results if r["status"] == BROKEN]
    throttled = [r for r in results if r["status"] == THROTTLED]
    redirected = [r for r in results if r["status"] == REDIRECT]
    skipped = [r for r in results if r["status"] == SKIPPED]

    lines = []
    for r in broken:
        lines.append(f"  BROKEN   {label(r):<22} {r['url']}\n           {r['detail']}")
    for r in throttled:
        lines.append(f"  throttled {label(r):<21} {r['url']}\n           {r['detail']}")
    for r in redirected:
        lines.append(f"  moved    {label(r):<22} {r['detail']}")
    for r in skipped:
        lines.append(f"  skipped  {label(r):<22} {r['detail']}")

    lines.append("")
    counts = [f"{len(broken)} broken", f"{len(redirected)} redirected"]
    if throttled:
        counts.append(f"{len(throttled)} throttled")
    counts.append(f"{len(skipped)} without a url")
    lines.append(f"{len(results)} checked: " + ", ".join(counts) + ".")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="check_links.py", description=__doc__.split("\n")[0])
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--timeout", type=float, default=10)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--fail-on-broken", action="store_true",
                        help="exit non-zero if any link is broken")
    args = parser.parse_args(argv)

    if args.workers < 1:
        parser.error("--workers must be at least 1")
    if args.timeout <= 0:
        parser.error("--timeout must be greater than 0")

    configure("WARNING")

    try:
        with open(config.AGENTS_JSON) as f:
            records = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"error: could not read {config.AGENTS_JSON}: {e}", file=sys.stderr)
        return 1

    results = check_catalogue(records, workers=args.workers, timeout=args.timeout)
    print(json.dumps(results, indent=2) if args.as_json else render(results))

    broken = any(r["status"] == BROKEN for r in results)
    return 1 if (broken and args.fail_on_broken) else 0


if __name__ == "__main__":
    sys.exit(main())
