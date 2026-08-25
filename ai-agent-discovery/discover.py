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


def canonical_tech(name):
    """One technology written several ways is one technology.

    GitHub reports the language as "Vue"; a curated stack is as likely to say
    "Vue.js", and both are right. Two copies of this rule disagreed once
    already — the audit stripped only a `.js` suffix while the catalogue guard
    also folded spaces and hyphens, so "Objective-C" against GitHub's
    "Objective C" satisfied the guard and still produced a stack finding.
    """
    return ((name or "").casefold().strip()
            .removesuffix(".js").replace(" ", "").replace("-", ""))

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
    "lecture", "learning path", "study guide",
    "paper list", "reading list", "resources for", "book",
    # The plural, not the singular: "example" alone rejected ChatterBot,
    # which "learns replies from example conversations" — there the word
    # describes training data. A repository that *is* a set of examples calls
    # itself "examples", as agent-examples and openai-cookbook do.
    "examples", "example project", "example app", "cookbook",
    "demo project", "sample code",
    # Widened after running the filter over five live topic searches: these
    # six describe teaching material and none of them appears anywhere in the
    # catalogue, which is the test every refusal phrase has to pass.
    # "from scratch in" missed "from scratch, step by step".
    # "from scratch" alone refused LitGPT — "readable from-scratch
    # implementations" is a description of a style, not a genre. The
    # tutorial idiom carries the step-by-step framing with it.
    # "learn how to" and "build it yourself" each let a top-starred repo
    # through: Made-With-ML opens "Learn how to develop, deploy and iterate",
    # and NASA's open-source-rover is "a build-it-yourself, 6-wheel rover" —
    # hardware, not software. Neither appears anywhere in the catalogue.
    "from scratch in", "build your own", "build it yourself", "learn how to",
    "step by step", "lesson", "zoomcamp",
    "best practice", "checklist",
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
# Phrases with no word boundary to anchor to. `\b` sits between a word and a
# non-word character, and CJK characters are word characters, so `\b从零开始\b`
# never matches inside 从零开始构建大模型 — "building a large model from scratch",
# which is a tutorial however it is written.
NOT_A_TOOL_UNANCHORED = re.compile("|".join(re.escape(p) for p in (
    "从零开始", "教程", "入门",
)))

NOT_A_TOOL_PATTERN = re.compile(
    r"\b(?:" + "|".join(re.escape(phrase)
                        for phrase in NOT_A_TOOL + CONFIG_COLLECTION) + r")s?\b")

# "interview" needs the company it keeps, which is why it is not in the list
# above. Bare, it refused STORM for researching a topic "by simulating expert
# interviews" — there the word is the method. A fixed phrase list does not
# work either: "interview prep" cannot match "interview preparation", and the
# `s?` above only pluralises the end of a phrase.
#
# The first attempt at this over-corrected badly. Matching "interview" near
# any of {prep, question, answer, guide, handbook, cheat}, plus a bare
# "technical|job|system design interview", refused an AI agent that "conducts
# technical interviews with candidates", one that "automates job interviews",
# and one that "runs customer interviews and turns the answers into a report"
# — a live category, silently dropped — while still letting "practice mock
# interviews with an LLM" through.
#
# So: only phrasings that describe studying *for* an interview, never ones
# that describe conducting one. "System design interviews explained" gets
# past this, and that is the deliberate trade — a prep repository reaching a
# reviewer costs one rejection, whereas refusing every AI interviewer costs
# a category nobody ever sees.
# A separator that a repository name and a sentence both use. The haystack is
# `name + description`, and GitHub names are hyphenated, so requiring literal
# whitespace let "interview-prep", "interview-questions" and
# "coding-interview-prep" straight through — every one of them refused by the
# looser pattern this replaced, and names are checked precisely because a
# prep repo names itself about as often as it describes itself.
_GAP = r"[\s\-_]+"

# Phrasings that only ever describe studying for an interview. No verb rescues
# these — "automated interview preparation" is still preparation. "Mock
# interviews" is not among them: an AI recruiter conducts those too, and
# refusing every AI interviewer costs a category nobody ever sees, so it sits
# with the other ambiguous phrase below. "Run mock interviews and grade
# yourself" gets through as a result — one rejection by a reviewer, against a
# whole category never reaching one.
INTERVIEW_PREP_PATTERN = re.compile(
    rf"\binterviews?{_GAP}prep\w*\b"
    rf"|\b(?:interviews?{_GAP}practice|practice{_GAP}interviews?)\b"
    rf"|\binterview{_GAP}(?:study|cheat)\w*\b"
    rf"|\bprepar\w+{_GAP}for{_GAP}(?:\w+{_GAP}){{0,2}}interviews?\b")

# The two phrases that cut both ways: a prep repository collects interview
# questions and holds mock interviews, and a recruiting agent generates the
# first and conducts the second. Kept apart from the pattern above because
# only these may be overridden by a verb — an override written as a
# short-circuit above the whole filter re-admitted "automated interview
# preparation" and "coding-interview-prep" too.
#
# The cost is that "run mock interviews and grade yourself" gets through: one
# rejection by a reviewer, against a whole category never reaching one.
INTERVIEW_QUESTIONS_PATTERN = re.compile(
    rf"\binterview{_GAP}questions?\b|\bmock{_GAP}interviews?\b")

# "course" three ways, none of which worked alone. The bare word refused an
# agent security scanner for "off course". Enumerating "course on", "crash
# course" and six more let huggingface/agents-course and mlcourse.ai through.
# A pair of fixed-space lookbehinds then refused "off-course", "over the
# course of", "course correction", "on course" and "obstacle course" — the
# hyphenated form of the very idiom it was written for.
#
# What separates them is not the word but where it sits. A repository that
# *is* a course usually says so in its name; in prose, the genre needs an
# article or a learning word beside it, and the idioms never have one.
# A repository *named* course almost always is one, and the name is where
# GitHub puts the genre: agents-course, llm-course, mlcourse.ai. Matched as a
# substring rather than a word, because "mlcourse" has no boundary before it.
# The English words that carry the same six letters are excluded by name:
# discourse, recourse and concourse — "discourse-ai" is a real tool the suite
# already guarded against.
COURSE_NAME_PATTERN = re.compile(r"(?<!re)(?<!dis)(?<!con)courses?")

# A tool that *produces* interview questions or *conducts* mock interviews is
# an interviewer's tool rather than study material. Stems, not whole words, so
# each reaches its inflections — `scor` catches "scoring".
INTERVIEW_TOOL_PATTERN = re.compile(
    r"\b(?:generat|creat|writ|draft|ask|conduct|run|automat|scor|transcrib)\w*"
    r"[\s\w]{0,20}?\binterview")

# In prose, only the forms that cannot be anything else. This took four
# attempts and each failure was the opposite of the last: the bare word
# refused an agent security scanner, an eight-phrase list let
# huggingface/agents-course through, a pair of lookbehinds refused
# "off-course" and "over the course of", and narrowing further dropped "a
# course for beginners" and "course repo" entirely.
#
# What survives is the genre with a learning word beside it. The bare "a
# course" and the trailing "<word> course" stay out — each reads as an idiom
# at least as often as a genre — and the name rule and the declared topics
# carry what that leaves, which is where the signal actually is.
COURSE_TEXT_PATTERN = re.compile(
    r"\bcourses\b"
    # A word may sit between: "Free MLOps course from DataTalks.Club" was
    # the phrasing that got mlops-zoomcamp past an adjacent-words rule.
    r"|\b(?:free|online|video|crash|introductory)\s+(?:\w+\s+)?course\b"
    r"|\bcourse\s+from\b"
    # Stems, like every other pattern here: "course covers" and "course
    # covered" were missed while "course covering" was caught.
    r"|\bcourse\s+(?:on|cover\w*|about|material\w*|note\w*|repo\w*|by)\b"
    # "a/the/this course" needs a word that only a taught course takes.
    # "for" and "in" were in this list and put back the idioms the previous
    # iteration deleted — "plots a course for a drone", "stay the course in
    # production". What is left cannot be steered or held.
    r"|\b(?:a|the|this)\s+course\s+(?:covering|about|that\s+teaches|i\s+teach|we\s+teach)\b"
    r"|\b(?:a|the|this)\s+course\s+(?:for|on)\s+"
    r"(?:beginners?|students?|newcomers?|anyone)\b"
    r"|\bcontains?\s+the\s+course\b")

# Topics a repository applies to itself when it is teaching rather than
# shipping. Far more reliable than reading the prose for it: a course can be
# described in any language — 从零开始构建智能体 was not going to match an English
# phrase list — but it still tags itself `tutorial`. Found by running the
# filter over five live topic searches and looking at what got through:
# seven of the twelve escapes were learning material, and every one declared
# itself here.
LEARNING_TOPICS = {
    "tutorial", "tutorials", "course", "courses", "教程",
    "learning", "learn", "education", "educational", "book", "ebook",
    "awesome", "awesome-list", "curated-list", "cheatsheet", "roadmap",
    "beginner", "beginners", "study", "handbook", "guide", "lessons",
}

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


def _flatten(text):
    """Separators as spaces, so a phrase reads a hyphenated repository name."""
    return re.sub(r"[\-_]+", " ", text)


def looks_like_a_tool(repo):
    """Whether this is software you would run, rather than something to read.

    Checked against the name, the description and the repository's own
    topics. A list names itself ("awesome-llm-apps") about as often as it
    describes itself, and a course tags itself `tutorial` whatever language
    it is written in.
    """
    declared = {t.casefold() for t in repo.get("topics") or []}
    if declared & LEARNING_TOPICS:
        return False

    name = (repo.get("name") or "").lower()
    described = (repo.get("description") or "").lower()
    haystack = f"{name} {described}"
    # Separators flattened before matching, so every phrase in the list reads
    # a hyphenated repository name too — "claude-code-best-practice" is the
    # same claim as "best practice", and GitHub names are always hyphenated.
    flattened = _flatten(haystack)
    if NOT_A_TOOL_PATTERN.search(flattened) is not None:
        return False
    if NOT_A_TOOL_UNANCHORED.search(haystack) is not None:
        return False
    # The name and the prose are asked different questions: "course" in a
    # repository name is the genre naming itself, while in a sentence it is
    # as likely to be "off course" or "course correction".
    if COURSE_NAME_PATTERN.search(name) is not None:
        return False
    # Flattened, like NOT_A_TOOL_PATTERN: "crash-course" is the same claim as
    # "crash course", and only the spaced form was being read.
    if COURSE_TEXT_PATTERN.search(_flatten(described)) is not None:
        return False
    if INTERVIEW_PREP_PATTERN.search(haystack) is not None:
        return False
    # Only the ambiguous phrase defers to the verb.
    if INTERVIEW_QUESTIONS_PATTERN.search(haystack) is not None:
        return INTERVIEW_TOOL_PATTERN.search(haystack) is not None
    return True


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


def why_unusable(repo):
    """Why a repository cannot become a record, or None if it can.

    Separated out because the reasons are not equivalent. "Not a tool" is the
    filter working. "No category matched" is a real tool being dropped, and
    dropping it silently is how sixteen of them went past in one run of five
    topics — rig, TradingAgents, graphiti and daytona among them.
    """
    name = (repo.get("name") or "").strip()
    description = (repo.get("description") or "").strip()

    if not name or not description:
        return "no description"
    # Asked before the length check, so the truer reason wins: a tutorial with
    # a six-word tagline is not a near miss, and reporting it as "description
    # too short" invites someone to go and lengthen it.
    if not looks_like_a_tool(repo):
        return "not a tool"
    if len(description) < MIN_DESCRIPTION:
        return "description too short"
    if infer_category(repo) is None:
        return "no category matched"
    if not infer_tech_stack(repo):
        return "no technologies found"
    return None


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
    # `.get`, not `[...]`: the near-miss path calls this with a raw search
    # result, and a repository with a null name raised AttributeError out of
    # the whole run — discarding every candidate already found with it.
    return (record.get("name") or "").strip().lower() not in names


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
    # Why each unknown repository was dropped, so a run says what it threw
    # away and not merely how much. Written after guessing wrong about it:
    # the categoriser looked like the bottleneck and is not — over five live
    # topics the reasons were 17 descriptions too short, 3 with no category
    # and 1 with no technologies. A count of "25 unusable" hid all of that.
    reasons, seen_near_misses = {}, set()
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
            reason = why_unusable(repo)
            if reason is not None:
                skipped["unusable"] += 1
                # "Not a tool" is the filter working and needs no listing;
                # the rest are near misses worth a maintainer's eye.
                # Keyed by url when there is no name: they would otherwise
                # all collapse onto "", so the first was reported as a blank
                # row and every later one dropped as a duplicate of it.
                full = repo.get("full_name") or repo.get("name") or ""
                key = full or repo.get("html_url") or None
                if (reason != "not a tool" and key
                        and key not in seen_near_misses
                        and is_new({"name": repo.get("name"),
                                    "url": repo.get("html_url") or ""},
                                   repos, names)):
                    # Deduplicated like the candidates themselves: the same
                    # repository is tagged with several of these topics, and
                    # reporting it five times inflates every count with it.
                    seen_near_misses.add(key)
                    reasons.setdefault(reason, []).append({
                        "name": full or repo.get("html_url") or "(unnamed)",
                        "stars": int(repo.get("stargazers_count") or 0),
                        "url": repo.get("html_url") or "",
                    })
                continue
            record = to_record(repo)
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
    for near in reasons.values():
        near.sort(key=lambda r: r["stars"], reverse=True)
    skipped["near_misses"] = reasons

    logger.info("%d candidate(s) from %d topic(s); skipped %d already known, %d unusable",
                len(found), searched, skipped["known"], skipped["unusable"])
    for reason, near in sorted(reasons.items(), key=lambda kv: -len(kv[1])):
        logger.info("%d near miss(es) — %s:", len(near), reason)
        for repo in near[:5]:
            logger.info("  %-38s %7d", repo["name"], repo["stars"])
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
