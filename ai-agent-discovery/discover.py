"""Find candidate agents on GitHub and propose them for review.

    python discover.py --dry-run            # show what would be proposed
    python discover.py                      # queue them for review
    python discover.py --topic ros --min-stars 2000

The catalogue is hand-curated, which is why it is any good and also why it
goes stale: nobody notices a tool that launched last month. This searches
GitHub for repositories matching the topics the catalogue already covers and
proposes the ones that are genuinely new.

Nothing is written to the catalogue. Every candidate goes through
`submissions.submit()`, so it lands in the same review queue a member of the
public would use and a maintainer still approves it by hand. That is the
whole reason this is safe to run on a schedule: the crawler's judgement is
advisory, and its mistakes cost a reviewer one click.

Unauthenticated requests are limited to 60/hour (10/minute for search). Set
GITHUB_TOKEN to raise that.
"""

import argparse
import json
import logging
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), 'backend')))

from refresh_stars import parse_repo  # noqa: E402

import config  # noqa: E402
import submissions  # noqa: E402
from admin import AdminError, load_catalogue  # noqa: E402
from logging_setup import configure  # noqa: E402

logger = logging.getLogger("discover")

SEARCH_URL = "https://api.github.com/search/repositories"

# Topics worth searching, chosen to match the categories the catalogue
# already has. A topic that returns mostly noise costs a reviewer time, so
# these are deliberately narrow.
DEFAULT_TOPICS = [
    "ai-agents", "llm-agent", "autonomous-agents", "rag", "llmops",
    "vector-database", "prompt-engineering", "llm-inference", "fine-tuning",
    "text-to-speech", "speech-recognition", "robotics", "ros2",
    "ai-safety", "llm-evaluation", "code-generation",
    # Automation, Customer Service and Data Analysis were mapped but
    # unreachable: no default topic led to any of them, so a scheduled run
    # could never propose one — and those are the thinnest categories.
    "browser-automation", "conversational-ai",
    # "data-analysis" was tried and returned pandas, superset, metabase and
    # goaccess — good software, none of it AI. These reach the same category
    # and return WrenAI, pycaret and FLAML instead.
    "text-to-sql", "automl",
]

# Topic to category. First match wins, so ordering is the decision.
#
# Ordered from what a tool *is* to what you can *do* with it. A repository
# tagged both "text-to-speech" and "fine-tuning" is a speech model that
# happens to be tunable, not a fine-tuning framework — with the technique
# rules first, CosyVoice was filed under Fine-tuning. Same reason
# "vector-database" loses to "rag", and a search engine is Infrastructure
# rather than Research.
TOPIC_CATEGORIES = [
    # Modality first: the most specific thing a repository can say.
    ("ros2", "Robotics"), ("ros", "Robotics"), ("robotics", "Robotics"),
    ("text-to-speech", "Multimodal"), ("speech-recognition", "Multimodal"),
    ("tts", "Multimodal"), ("asr", "Multimodal"), ("voice-cloning", "Multimodal"),
    ("stable-diffusion", "Multimodal"), ("computer-vision", "Multimodal"),
    ("ocr", "Multimodal"), ("multimodal", "Multimodal"),
    ("reinforcement-learning", "Robotics"),

    # Then the job the tool does.
    ("code-generation", "Code Generation"), ("copilot", "Code Generation"),
    ("code-review", "Code Generation"), ("developer-tools", "Code Generation"),
    ("chatbot", "Customer Service"), ("customer-support", "Customer Service"),
    ("conversational-ai", "Customer Service"),
    ("data-analysis", "Data Analysis"), ("data-visualization", "Data Analysis"),
    ("text-to-sql", "Data Analysis"), ("automl", "Data Analysis"),
    ("web-scraping", "Automation"), ("browser-automation", "Automation"),
    ("workflow-automation", "Automation"), ("automation", "Automation"),
    ("autonomous-agents", "Autonomous Agent"), ("agi", "Autonomous Agent"),
    ("rag", "Research"), ("retrieval-augmented-generation", "Research"),
    ("knowledge-base", "Research"),

    # Then where it sits in a stack.
    ("search-engine", "Infrastructure"), ("vector-database", "Infrastructure"),
    ("vector-search", "Infrastructure"), ("semantic-search", "Infrastructure"),
    ("llm-inference", "Infrastructure"), ("model-serving", "Infrastructure"),
    ("llmops", "MLOps"), ("mlops", "MLOps"), ("experiment-tracking", "MLOps"),
    ("data-pipelines", "MLOps"),

    # Techniques last: they describe what you can do with a tool, which is
    # true of many tools that are better described by something above.
    ("ai-safety", "Safety"), ("guardrails", "Safety"),
    ("red-teaming", "Safety"), ("prompt-injection", "Safety"),
    ("llm-evaluation", "Evaluation"), ("observability", "Evaluation"),
    ("llm-observability", "Evaluation"), ("benchmark", "Evaluation"),
    ("fine-tuning", "Fine-tuning"), ("lora", "Fine-tuning"),
    ("rlhf", "Fine-tuning"), ("peft", "Fine-tuning"),
    ("ai-agents", "Framework"), ("llm-agent", "Framework"),
    ("agent-framework", "Framework"), ("llm-framework", "Framework"),
    ("prompt-engineering", "Framework"),
]

# A use case per category, so a proposal arrives with the field populated.
# Deliberately generic — the reviewer knows the tool better than the crawler
# does, and a vague-but-true phrase is easier to correct than a wrong one.
CATEGORY_USE_CASES = {
    "Robotics": "Robotics development",
    "Fine-tuning": "Adapting a model",
    "Multimodal": "Speech and vision",
    "Safety": "Guarding model behaviour",
    "Evaluation": "Measuring model quality",
    "Code Generation": "Writing and reviewing code",
    "Research": "Question answering over documents",
    "Infrastructure": "Serving and storing models",
    "MLOps": "Running ML in production",
    "Customer Service": "Automating support",
    "Data Analysis": "Exploring data",
    "Automation": "Automating a workflow",
    "Autonomous Agent": "Running a task end to end",
    "Framework": "Building an agent",
}

# GitHub's language field is whatever the repo has most bytes of, which is
# not always a technology anyone would list. autoware reports "Dockerfile".
LANGUAGE_NAMES = {
    "Jupyter Notebook": "Jupyter",
    "Dockerfile": "Docker",
    "CMake": "C++",
}

# Markup, build glue and packaging. Being mostly these says how a repository
# is assembled, not what it is built with, so they are dropped rather than
# renamed — the topics usually supply something better.
NOT_A_TECH_STACK = {
    "HTML", "CSS", "SCSS", "Makefile", "Batchfile", "Roff", "M4",
    "Shell", "PowerShell", "Vim Script", "TeX", "MDX", "Nix",
}

# Topics that name a real technology, worth carrying into tech_stack.
TECH_TOPICS = {
    "pytorch": "PyTorch", "tensorflow": "TensorFlow", "jax": "JAX",
    "langchain": "LangChain", "llamaindex": "LlamaIndex", "fastapi": "FastAPI",
    "react": "React", "nextjs": "Next.js", "docker": "Docker",
    "kubernetes": "Kubernetes", "ros2": "ROS 2", "cuda": "CUDA",
    "postgresql": "PostgreSQL", "rust": "Rust",
}

# Taken from the queue rather than restated, so the crawler cannot propose
# something the queue would then refuse.
MIN_DESCRIPTION = submissions.MIN_DESCRIPTION

# How recently a repository must have been pushed to be worth proposing.
# Shorter than audit.py's 18-month dormancy line, and deliberately so: that
# one asks "has an entry we already vetted gone quiet", this one asks "is this
# worth a reviewer's attention at all", and a project silent for a year is
# not. Applied by default rather than only when a caller remembers — a bare
# `make discover` was proposing projects two years dead.
DEFAULT_FRESH_MONTHS = 6

# Reading lists, tutorials and books dominate a stars-sorted topic search —
# "awesome-llm-apps" outranks every actual tool by an order of magnitude.
# They are not agents, so no reviewer would ever accept one; filtering here
# is the difference between a useful queue and a page of noise to dismiss.
# Every phrase here is checked against the catalogue by
# test_no_catalogue_entry_would_be_rejected: an entry a maintainer accepted
# is a tool by definition, so a phrase that rejects one is too broad.
# "collection of" rejected MCP Servers ("the reference collection of Model
# Context Protocol servers"), "paper" rejected PaperQA ("scientific papers"),
# and "boilerplate" rejected Jina Reader ("stripping navigation and
# boilerplate"). All three were dropped for narrower forms.
NOT_A_TOOL = (
    "awesome", "curated list", "curated collection", "collection of awesome",
    "collection of resources", "collection of links",
    "tutorial", "roadmap", "cheatsheet", "cheat sheet", "handbook",
    "course", "lecture", "learning path", "study guide", "interview",
    "paper list", "reading list", "resources for", "book",
    # The plural, not the singular: "example" alone rejected ChatterBot,
    # which "learns replies from example conversations" — there the word
    # describes training data. A repository that *is* a set of examples calls
    # itself "examples", as agent-examples and openai-cookbook do.
    "examples", "example project", "example app", "cookbook",
    "demo project", "sample code",
    "from scratch in", "build your own",
)

# Configuration for *other* agents, rather than software in its own right:
# prompt dumps, skill packs, plugin marketplaces. These rank highly because
# they are genuinely popular, and they are not agents — the catalogue would
# be listing someone's Claude Code settings next to Ollama.
#
# Phrased narrowly on purpose, and narrowed again after the first attempt
# rejected real tools. "prompt" alone rejects Prompt Optimizer; "slash
# command" and "custom command" reject every terminal agent and Discord bot —
# which is what the conversational-ai topic returns, so the filter was
# cancelling the topic added to reach Customer Service. "marketplace for" and
# "skills for" reject an agent marketplace and a tool that *adds* skills.
CONFIG_COLLECTION = (
    "system prompt", "leaked prompt", "extracted prompt", "prompt collection",
    "prompt library", "agent skill", "skill pack", "plugin marketplace",
    "cursor rule", "dotfile", "rules for claude",
    # "<thing> for <a named agent product>" is the shape these take. Naming
    # the products keeps it from matching a tool that merely integrates with
    # one — an MCP server "for Claude Code" is real software.
    "skills for claude", "skills for cursor", "skills for codex",
    "commands for claude",
)

# Matched on word boundaries, with an optional plural. As plain substrings
# these rejected real tools: "book" is inside "notebook" and "facebook",
# "course" inside "discourse", "paper" inside "wallpaper".
NOT_A_TOOL_PATTERN = re.compile(
    r"\b(?:" + "|".join(re.escape(phrase)
                        for phrase in NOT_A_TOOL + CONFIG_COLLECTION) + r")s?\b")

# "robotics" is the topic RPA projects use — EasySpider and Wechaty are both
# tagged it — so the word alone cannot decide the category. A repo claiming
# robotics while describing process automation is filed by what it says.
RPA_HINTS = ("rpa", "robotic process", "process automation", "web scraping",
             "scraper", "crawler", "chatbot", "workflow")


class RateLimited(Exception):
    """GitHub refused the request because the quota is exhausted."""


def fresh_since(months=DEFAULT_FRESH_MONTHS, today=None):
    """The `pushed:` cutoff date, as GitHub wants it."""
    today = today or datetime.now(timezone.utc).date()
    return (today - timedelta(days=round(months * 30.44))).isoformat()


def build_query(topic, min_stars, pushed_since=None):
    """A GitHub search query for one topic.

    Two separate filters, because they catch different things. `pushed:`
    excludes projects that were popular once and went quiet, which is most of
    what a stars-only search returns. `archived:false` excludes projects whose
    authors have declared them finished — and a repository can be archived
    *and* recently pushed, so the first filter does not imply the second:
    microsoft/TaskWeaver was archived with 6,176 stars and a push inside any
    six-month window, and came back as a candidate until this was added.
    """
    parts = [f"topic:{topic}", f"stars:>={min_stars}", "archived:false"]
    if pushed_since:
        parts.append(f"pushed:>={pushed_since}")
    return " ".join(parts)


class SearchFailed(Exception):
    """One search could not be completed at all."""


def search_repos(query, token=None, limit=30, timeout=15):
    """Return repositories matching `query`, most-starred first.

    Raises SearchFailed rather than returning [] when the request could not
    be made: "this topic has no new repositories" and "this topic was never
    searched" are opposite outcomes, and the caller must not conflate them.
    """
    params = urllib.parse.urlencode({
        "q": query,
        "sort": "stars",
        "order": "desc",
        "per_page": min(limit, 100),
    })
    request = urllib.request.Request(
        f"{SEARCH_URL}?{params}",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "ai-agent-discovery-discover",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response).get("items", [])[:limit]
    except urllib.error.HTTPError as e:
        if e.code in (403, 429):
            raise RateLimited(
                "GitHub rate limit reached; set GITHUB_TOKEN to raise it.") from e
        raise SearchFailed(f"HTTP {e.code}") from e
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as e:
        raise SearchFailed(str(e)) from e


def looks_like_a_tool(repo):
    """Whether this is software you would run, rather than something to read.

    Checked against the name and the description: a list names itself
    ("awesome-llm-apps") about as often as it describes itself.
    """
    haystack = f"{repo.get('name') or ''} {repo.get('description') or ''}".lower()
    return NOT_A_TOOL_PATTERN.search(haystack) is None


def infer_category(repo):
    """Pick a category from the repository's topics.

    Returns None when nothing matches, which is treated as "not a fit" rather
    than filed under a default — a wrong category is worse than no proposal,
    because it teaches the catalogue's own structure something false.
    """
    topics = [t.lower() for t in repo.get("topics") or []]
    described = f"{repo.get('name') or ''} {repo.get('description') or ''}".lower()

    for topic, category in TOPIC_CATEGORIES:
        if topic not in topics:
            continue
        if category == "Robotics" and any(hint in described for hint in RPA_HINTS):
            # Tagged robotics but describing process automation. Skip this
            # match and let a later topic decide; filing it under Robotics
            # would teach the catalogue's own structure something false.
            continue
        return category
    return None


def infer_tech_stack(repo):
    """Language plus any topic that names a real technology."""
    stack = []
    language = repo.get("language")
    if language and language not in NOT_A_TECH_STACK:
        stack.append(LANGUAGE_NAMES.get(language, language))

    for topic in repo.get("topics") or []:
        tech = TECH_TOPICS.get(topic.lower())
        if tech and tech not in stack:
            stack.append(tech)

    return stack[:5]


def to_record(repo):
    """Shape a repository into a catalogue record, or None if unusable.

    A repository is skipped rather than patched up when a required field
    cannot be filled honestly. Guessing here would just move the work to the
    reviewer while making it look like it was already done.
    """
    name = (repo.get("name") or "").strip()
    description = (repo.get("description") or "").strip()

    if not name or not description:
        return None
    if len(description) < MIN_DESCRIPTION:
        return None
    if not looks_like_a_tool(repo):
        return None

    category = infer_category(repo)
    if category is None:
        return None

    stack = infer_tech_stack(repo)
    if not stack:
        return None

    return {
        "name": name,
        "description": description,
        "category": category,
        "tech_stack": stack,
        "github_stars": int(repo.get("stargazers_count") or 0),
        "url": repo.get("html_url") or "",
        "use_case": CATEGORY_USE_CASES.get(category, ""),
    }


def known_repos(records):
    """Every "owner/name" the catalogue already has, plus every name."""
    repos, names = set(), set()
    for record in records:
        repo = parse_repo(record.get("url"))
        if repo:
            repos.add(repo.lower())
        names.add((record.get("name") or "").strip().lower())
    return repos, names


def is_new(record, repos, names):
    """Whether this record duplicates something already known.

    Checked on the repository rather than the URL, so a trailing slash or an
    http/https difference does not read as a different project.
    """
    repo = parse_repo(record.get("url"))
    if repo and repo.lower() in repos:
        return False
    return record["name"].strip().lower() not in names


# GitHub allows 10 search requests a minute unauthenticated, 30 with a token.
# Six seconds between topics keeps a full unauthenticated run inside the
# budget; a token relaxes it.
PAUSE_ANONYMOUS = 6.5
PAUSE_WITH_TOKEN = 2.0


def discover(topics, min_stars, token=None, limit=30, pushed_since=None, pause=None):
    """Search each topic and return the candidate records, best first.

    Deduplicated across topics as well as against the catalogue: the same
    repository is tagged with several of these topics, and proposing it three
    times would be three rejections for one decision.
    """
    catalogue = load_catalogue()
    pending = [e["agent"] for e in submissions.read_all(status=submissions.PENDING)
               if isinstance(e.get("agent"), dict)]
    repos, names = known_repos(catalogue + pending)

    if pause is None:
        pause = PAUSE_WITH_TOKEN if token else PAUSE_ANONYMOUS

    found, skipped = [], {"known": 0, "unusable": 0}
    searched, failed = 0, []
    limited = None
    for index, topic in enumerate(topics):
        if index and pause:
            # Search is limited far more tightly than the rest of the API.
            time.sleep(pause)

        query = build_query(topic, min_stars, pushed_since)
        logger.info("Searching %s", query)

        try:
            results = search_repos(query, token=token, limit=limit)
        except RateLimited as e:
            # Stop searching, but keep what has already been found: the run
            # so far cost real API budget, and throwing it away means the
            # next run spends that budget again to learn the same thing.
            logger.warning("%s Stopping with %d candidate(s) already found.", e, len(found))
            failed.extend(topics[index:])
            limited = e
            break
        except SearchFailed as e:
            logger.warning("search %r failed: %s", query, e)
            failed.append(topic)
            continue
        searched += 1

        for repo in results:
            record = to_record(repo)
            if record is None:
                skipped["unusable"] += 1
                continue
            if not is_new(record, repos, names):
                skipped["known"] += 1
                continue

            found.append(record)
            # Claim it now so a later topic does not propose it again.
            claimed = parse_repo(record["url"])
            if claimed:
                repos.add(claimed.lower())
            names.add(record["name"].strip().lower())

    if limited and not searched:
        # Nothing was looked at and the reason is actionable, so let it
        # reach the caller intact — "none of the topics could be searched"
        # would drop the one instruction that fixes it.
        raise limited
    if failed and not searched:
        # Reporting "nothing new" here would be a lie that reads as success,
        # and on a schedule it would look like the catalogue is current when
        # in fact nothing has been checked for weeks.
        raise SearchFailed(
            f"none of the {len(failed)} topic(s) could be searched: {', '.join(failed)}")
    if limited:
        logger.warning(
            "Searched %d of %d topic(s) before the limit. %s",
            searched, len(topics), limited)
    if failed:
        logger.warning("%d of %d topic(s) could not be searched: %s",
                       len(failed), len(topics), ", ".join(failed))

    found.sort(key=lambda r: r["github_stars"], reverse=True)
    logger.info("%d candidate(s) from %d topic(s); skipped %d already known, %d unusable",
                len(found), searched, skipped["known"], skipped["unusable"])
    return found, skipped


def format_candidate(record):
    return (f"  {record['name']:<24} {record['github_stars']:>7,}  "
            f"{record['category']:<18} {record['url']}")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="discover.py", description=__doc__.split("\n")[0])
    parser.add_argument("--topic", action="append", dest="topics",
                        help="topic to search (repeatable; defaults to a built-in list)")
    parser.add_argument("--min-stars", type=int, default=1000,
                        help="ignore repositories below this many stars (default: 1000)")
    parser.add_argument("--limit", type=int, default=30,
                        help="results per topic (default: 30)")
    parser.add_argument("--max-proposals", type=int, default=10,
                        help="stop after queueing this many (default: 10)")
    parser.add_argument("--pushed-since", default=None,
                        help=f"only repositories pushed since this date "
                             f"(default: {DEFAULT_FRESH_MONTHS} months ago)")
    parser.add_argument("--dry-run", action="store_true",
                        help="report candidates without queueing them")
    parser.add_argument("--json", action="store_true", dest="as_json",
                        help="print candidates as JSON (implies --dry-run)")
    parser.add_argument("--token", default=os.getenv("GITHUB_TOKEN"),
                        help="GitHub token (or set GITHUB_TOKEN)")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    configure("DEBUG" if args.verbose else "INFO")

    # JSON output is for a caller that wants the candidates, not for one that
    # wants them queued — writing to the queue as a side effect of asking for
    # a listing would surprise anyone piping this.
    if args.as_json:
        args.dry_run = True

    if not args.dry_run and not config.ENABLE_SUBMISSIONS:
        logger.error("Submissions are disabled; set ENABLE_SUBMISSIONS=true or use --dry-run.")
        return 1

    try:
        found, _ = discover(
            args.topics or DEFAULT_TOPICS,
            min_stars=args.min_stars,
            token=args.token,
            limit=args.limit,
            pushed_since=args.pushed_since or fresh_since(),
        )
    except RateLimited as e:
        logger.error("%s", e)
        return 1
    except SearchFailed as e:
        logger.error("Discovery failed: %s", e)
        return 1

    proposals = found[:args.max_proposals]

    if args.as_json:
        # Always valid JSON, including when there is nothing — a caller
        # parsing this should not have to special-case the empty run.
        print(json.dumps(proposals, indent=2))
        return 0

    if not found:
        logger.info("Nothing new found.")
        return 0

    print(f"\n{len(proposals)} candidate(s):")
    for record in proposals:
        print(format_candidate(record))

    if args.dry_run:
        print("\nDry run; nothing was queued.")
        return 0

    queued, failed = 0, []
    for record in proposals:
        try:
            submissions.submit(record)
            queued += 1
        except AdminError as e:
            # A rejection here is the queue doing its job — a duplicate that
            # appeared since the catalogue was read, or a full queue.
            failed.append((record["name"], str(e)))

    print(f"\nQueued {queued} for review.")
    for name, reason in failed:
        print(f"  not queued: {name} — {reason}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
