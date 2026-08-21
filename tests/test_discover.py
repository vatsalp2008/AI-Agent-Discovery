"""The GitHub discovery crawler.

Everything here runs against fixture payloads rather than the network. The
value of this module is entirely in what it *rejects* — a crawler that
proposes reading lists and mis-filed repositories costs a reviewer more time
than it saves — so most of these are tests that something is skipped.
"""

import json
import sys
from pathlib import Path

import pytest

import config

sys.path.insert(0, str(config.PACKAGE_DIR))

import discover  # noqa: E402


def repo(**overrides):
    """A GitHub search result that would be accepted."""
    base = {
        "name": "SomeAgent",
        "description": "An agent framework for building and running tool-using assistants.",
        "topics": ["ai-agents", "python"],
        "language": "Python",
        "stargazers_count": 4200,
        "html_url": "https://github.com/acme/someagent",
    }
    base.update(overrides)
    return base


class TestCategoryInference:
    def test_a_known_topic_picks_its_category(self):
        assert discover.infer_category(repo(topics=["robotics"])) == "Robotics"

    def test_the_earlier_rule_wins(self):
        """A repo tagged both rag and vector-database is more useful under
        Research; the ordering of TOPIC_CATEGORIES is the decision."""
        assert discover.infer_category(repo(topics=["vector-database", "rag"])) == "Research"

    @pytest.mark.parametrize("topics,expected,why", [
        (["fine-tuning", "text-to-speech"], "Multimodal",
         "a speech model that happens to be tunable is not a fine-tuning framework"),
        (["lora", "computer-vision"], "Multimodal",
         "same, for vision"),
        (["llm-evaluation", "robotics"], "Robotics",
         "a robotics project with benchmarks is still robotics"),
        (["search-engine", "semantic-search"], "Infrastructure",
         "a search engine is a component, not a research assistant"),
    ])
    def test_what_a_tool_is_beats_what_you_can_do_with_it(self, topics, expected, why):
        """CosyVoice arrived filed under Fine-tuning because the technique
        rules came first. Modality is the more specific claim."""
        assert discover.infer_category(repo(topics=topics)) == expected, why

    def test_a_technique_still_wins_when_it_is_all_there_is(self):
        assert discover.infer_category(repo(topics=["fine-tuning", "lora"])) == "Fine-tuning"

    def test_an_unmatched_topic_yields_nothing(self):
        """None means "not a fit", not "use a default" — a wrong category is
        worse than no proposal."""
        assert discover.infer_category(repo(topics=["baking", "knitting"])) is None

    def test_no_topics_at_all_yields_nothing(self):
        assert discover.infer_category(repo(topics=[])) is None
        assert discover.infer_category(repo(topics=None)) is None

    def test_topics_are_matched_case_insensitively(self):
        assert discover.infer_category(repo(topics=["Robotics"])) == "Robotics"

    def test_process_automation_is_not_filed_as_robotics(self):
        """RPA projects tag themselves "robotics". EasySpider and Wechaty
        both do, and both are as far from robotics as software gets."""
        rpa = repo(name="EasySpider",
                   description="A visual code-free web crawler and RPA tool for scraping data.",
                   topics=["robotics", "web-scraping"])
        assert discover.infer_category(rpa) != "Robotics"

    def test_a_real_robotics_project_is_still_robotics(self):
        real = repo(name="openpilot",
                    description="An operating system for robotics that upgrades driver assistance.",
                    topics=["robotics"])
        assert discover.infer_category(real) == "Robotics"

    def test_every_mapped_category_exists_in_the_catalogue(self):
        """A category the crawler invents would fragment the facets — the
        catalogue would gain "LLMOps" alongside the real "MLOps"."""
        catalogue = json.loads(Path(config.AGENTS_JSON).read_text())
        real = {r["category"] for r in catalogue}

        mapped = {category for _, category in discover.TOPIC_CATEGORIES}
        assert mapped <= real, f"crawler would invent categories: {sorted(mapped - real)}"

    def test_every_mapped_category_has_a_use_case(self):
        mapped = {category for _, category in discover.TOPIC_CATEGORIES}
        missing = mapped - set(discover.CATEGORY_USE_CASES)
        assert not missing, f"no use_case for: {sorted(missing)}"


class TestRejectingNonTools:
    @pytest.mark.parametrize("name,description", [
        ("awesome-llm-apps", "A collection of awesome LLM apps with AI agents and RAG."),
        ("Prompt-Engineering-Guide", "Guides, papers and resources for prompt engineering."),
        ("llm-course", "A course to get into large language models with roadmaps and notebooks."),
        ("ml-cookbook", "A cookbook of examples for building things with language models."),
        ("agents-from-scratch", "Build your own agent from scratch in pure Python, step by step."),
    ])
    def test_reading_material_is_not_proposed(self, name, description):
        """Stars-sorted topic search is dominated by lists — awesome-llm-apps
        outranks every actual tool by an order of magnitude."""
        assert not discover.looks_like_a_tool(repo(name=name, description=description))

    @pytest.mark.parametrize("name,description", [
        ("agent-notebooks", "Jupyter notebooks and tooling for running agents end to end."),
        ("discourse-ai", "Adds AI features to Discourse forums, including summaries."),
        ("wallpapers-ai", "Generates desktop wallpapers from a prompt using diffusion."),
        ("facebook-thing", "A tool from Facebook for training multimodal models at scale."),
    ])
    def test_a_word_inside_a_longer_word_is_not_a_match(self, name, description):
        """Matched as plain substrings these were all rejected: "book" is
        inside "notebook" and "facebook", "course" inside "discourse",
        "paper" inside "wallpaper"."""
        assert discover.looks_like_a_tool(repo(name=name, description=description))

    @pytest.mark.parametrize("name,description", [
        ("ml-books", "Free books on machine learning, updated weekly."),
        ("llm-courses", "Courses covering large language models from the ground up."),
        ("agent-examples", "Examples showing how to build an agent, step by step."),
    ])
    def test_the_plural_is_matched_too(self, name, description):
        assert not discover.looks_like_a_tool(repo(name=name, description=description))

    def test_no_catalogue_entry_would_be_rejected(self):
        """The catalogue is the definition of "this is a tool" — a
        maintainer accepted every entry. Any phrase that rejects one is too
        broad, and this is how three were caught: "collection of" rejected
        MCP Servers, "paper" rejected PaperQA, "boilerplate" rejected Jina
        Reader. All three read as obviously correct in a list.
        """
        catalogue = json.loads(Path(config.AGENTS_JSON).read_text())

        rejected = [r["name"] for r in catalogue
                    if not discover.looks_like_a_tool(
                        {"name": r["name"], "description": r["description"]})]
        assert not rejected, f"the crawler would refuse these real agents: {rejected}"

    @pytest.mark.parametrize("name,description", [
        ("system_prompts_leaks", "Extracted system prompts from Anthropic and OpenAI, updated regularly."),
        ("claude-skills", "345 Claude Code skills and agent skills, with 70+ custom commands."),
        ("agents", "Multi-harness agentic plugin marketplace for Claude Code, Cursor and Codex."),
        ("research-skills", "Academic Research Skills for Claude Code: research, write, review."),
        ("my-dotfiles", "My dotfiles and configs for every coding agent I use daily."),
    ])
    def test_configuration_for_other_agents_is_not_an_agent(self, name, description):
        """These rank highly because they are genuinely popular, and they are
        not tools — the catalogue would list someone's Claude Code settings
        next to Ollama."""
        assert not discover.looks_like_a_tool(repo(name=name, description=description))

    @pytest.mark.parametrize("name,description", [
        ("prompt-optimizer", "Rewrites and scores prompts against a model, making prompt tuning measurable."),
        ("skill-library", "A reusable skill library for robot manipulation, trained from demonstrations."),
        ("paper-qa", "Answers questions over scientific papers with citations, built for accuracy."),
        # Every one of these was rejected by the first version of the
        # configuration filter.
        ("opencode-cli", "Terminal agent with slash commands, tool use and MCP support for coding."),
        ("discord-ai-bot", "A Discord bot that answers questions, with slash commands and threads."),
        ("agent-market", "An open marketplace for AI agents you can run locally on your machine."),
        ("llm-skills", "Adds skills for browsing, coding and search to any LLM agent you run."),
        ("devin-like", "An AI software engineer with custom commands and a planning loop."),
        ("mcp-database", "An MCP server exposing your database to Claude Code and other clients."),
    ])
    def test_a_tool_that_merely_mentions_those_words_survives(self, name, description):
        """A filter that rejects real tools costs more than it saves. "slash
        command" rejected every terminal agent and Discord bot — which is
        exactly what the conversational-ai topic returns, so the filter was
        cancelling out the topic added to reach Customer Service."""
        assert discover.looks_like_a_tool(repo(name=name, description=description))

    def test_an_actual_tool_passes(self):
        assert discover.looks_like_a_tool(repo())

    def test_the_check_reads_the_name_as_well_as_the_description(self):
        """A list names itself about as often as it describes itself."""
        assert not discover.looks_like_a_tool(
            repo(name="awesome-agents", description="Everything you need in one place, updated weekly."))


class TestBuildingARecord:
    def test_a_good_repository_becomes_a_record(self):
        record = discover.to_record(repo())
        assert record["name"] == "SomeAgent"
        assert record["category"] == "Framework"
        assert record["github_stars"] == 4200
        assert record["use_case"]

    def test_a_thin_description_is_skipped(self):
        """The description is what gets embedded; a tagline retrieves badly.
        Same bar as the catalogue's own guard."""
        assert discover.to_record(repo(description="An agent.")) is None

    def test_a_missing_description_is_skipped(self):
        assert discover.to_record(repo(description=None)) is None

    def test_a_repository_with_no_recognisable_category_is_skipped(self):
        assert discover.to_record(repo(topics=["knitting"])) is None

    def test_a_repository_with_no_detectable_stack_is_skipped(self):
        assert discover.to_record(repo(language=None, topics=["ai-agents"])) is None

    def test_the_stack_carries_the_language_and_known_topics(self):
        record = discover.to_record(repo(language="Python", topics=["ai-agents", "pytorch"]))
        assert record["tech_stack"] == ["Python", "PyTorch"]

    def test_the_stack_is_capped(self):
        record = discover.to_record(repo(topics=["ai-agents", *discover.TECH_TOPICS]))
        assert len(record["tech_stack"]) <= 5

    def test_a_produced_record_passes_the_editor_validation(self):
        """The crawler feeds submissions.submit(), which validates. A record
        that cannot pass would be a crash on a schedule."""
        import admin

        record = discover.to_record(repo())
        # validate() fills in the fields a crawled record omits — status
        # defaults to active — so compare on what the crawler actually sets.
        cleaned = admin.validate(record, [])
        assert {k: cleaned[k] for k in record} == record
        assert cleaned["status"] == "active"


class TestDeduplication:
    def test_a_repository_already_in_the_catalogue_is_not_new(self):
        repos, names = discover.known_repos(
            [{"name": "PandasAI", "url": "https://github.com/sinaptik-ai/pandas-ai"}])
        assert not discover.is_new(
            {"name": "Something Else", "url": "https://github.com/sinaptik-ai/pandas-ai"},
            repos, names)

    def test_the_comparison_ignores_url_formatting(self):
        """A trailing slash or a case difference is the same project."""
        repos, names = discover.known_repos(
            [{"name": "PandasAI", "url": "https://github.com/sinaptik-ai/pandas-ai"}])
        assert not discover.is_new(
            {"name": "X", "url": "https://github.com/Sinaptik-AI/Pandas-AI/"}, repos, names)

    def test_a_name_already_taken_is_not_new(self):
        """Even at a different URL: two entries called the same thing are
        indistinguishable in search results."""
        repos, names = discover.known_repos([{"name": "Aider", "url": ""}])
        assert not discover.is_new({"name": "aider", "url": "https://github.com/x/y"}, repos, names)

    def test_an_unrelated_repository_is_new(self):
        repos, names = discover.known_repos([{"name": "Aider", "url": "https://github.com/a/b"}])
        assert discover.is_new({"name": "Zzz", "url": "https://github.com/c/d"}, repos, names)


class TestQueryBuilding:
    def test_the_query_carries_the_topic_and_the_floor(self):
        assert discover.build_query("rag", 1000) == (
            "topic:rag stars:>=1000 archived:false")

    def test_a_date_filters_out_abandoned_projects(self):
        query = discover.build_query("rag", 1000, "2026-01-01")
        assert "pushed:>=2026-01-01" in query

    def test_archived_repositories_are_excluded_server_side(self):
        """A recent push does not mean a live project.

        microsoft/TaskWeaver was archived at 6,176 stars with a push inside
        any six-month window, so `pushed:` let it through every time; it had
        to be rejected by hand. Filtering in the query rather than after the
        fact also stops archived repos consuming the per-topic result budget.
        """
        assert "archived:false" in discover.build_query("agent", 1000)
        assert "archived:false" in discover.build_query("agent", 1000, "2026-01-01")


class TestFreshnessDefault:
    """A bare `make discover` used to apply no recency filter at all, which is
    how six two-year-dead projects reached a reviewer in one sitting."""

    def test_the_cutoff_is_months_back_from_today(self):
        import datetime

        cutoff = discover.fresh_since(6, today=datetime.date(2026, 8, 18))
        assert cutoff == "2026-02-16"

    def test_a_bare_run_still_filters_by_date(self, monkeypatch):
        seen = []
        monkeypatch.setattr(discover, "discover",
                            lambda *a, **kw: (seen.append(kw.get("pushed_since")), ([], {}))[1])
        discover.main(["--json"])
        assert seen and seen[0], "no recency filter was applied"

    def test_an_explicit_date_still_wins(self, monkeypatch):
        seen = []
        monkeypatch.setattr(discover, "discover",
                            lambda *a, **kw: (seen.append(kw.get("pushed_since")), ([], {}))[1])
        discover.main(["--json", "--pushed-since", "2025-01-01"])
        assert seen == ["2025-01-01"]

    def test_every_default_topic_maps_to_a_category(self):
        """Searching a topic the crawler cannot then categorise burns API
        quota to produce nothing."""
        mapped = {topic for topic, _ in discover.TOPIC_CATEGORIES}
        unmapped = [t for t in discover.DEFAULT_TOPICS if t not in mapped]
        assert not unmapped, f"topics searched but never categorised: {unmapped}"


class TestTheDiscoveryRun:
    """The orchestration: what gets searched, deduplicated and reported."""

    @pytest.fixture
    def isolated(self, tmp_path, monkeypatch):
        """An empty catalogue and queue, so results are the crawler's alone."""
        catalogue = tmp_path / "agents.json"
        catalogue.write_text("[]")
        monkeypatch.setattr(config, "AGENTS_JSON", catalogue)
        monkeypatch.setattr(config, "SUBMISSIONS_PATH", tmp_path / "queue.jsonl")
        return tmp_path

    def stub_search(self, monkeypatch, by_topic):
        """Replace the network call; `by_topic` maps a topic to results or an
        exception to raise."""
        def fake(query, **kwargs):
            topic = query.split()[0].removeprefix("topic:")
            outcome = by_topic.get(topic, [])
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        monkeypatch.setattr(discover, "search_repos", fake)

    def test_results_come_back_best_first(self, isolated, monkeypatch):
        self.stub_search(monkeypatch, {"ai-agents": [
            repo(name="Small", stargazers_count=10, html_url="https://github.com/a/small"),
            repo(name="Big", stargazers_count=9000, html_url="https://github.com/a/big"),
        ]})
        found, _ = discover.discover(["ai-agents"], min_stars=0, pause=0)
        assert [r["name"] for r in found] == ["Big", "Small"]

    def test_the_same_repository_is_proposed_once_across_topics(self, isolated, monkeypatch):
        """These topics overlap heavily. Proposing one project three times
        is three rejections for one decision."""
        shared = repo(name="Shared", topics=["ai-agents", "rag"],
                      html_url="https://github.com/a/shared")
        self.stub_search(monkeypatch, {"ai-agents": [shared], "rag": [shared]})

        found, _ = discover.discover(["ai-agents", "rag"], min_stars=0, pause=0)
        assert [r["name"] for r in found] == ["Shared"]

    def test_something_already_in_the_catalogue_is_skipped(self, isolated, monkeypatch):
        (isolated / "agents.json").write_text(json.dumps([{
            "name": "Known", "url": "https://github.com/a/known", "description": "d",
            "category": "Framework", "tech_stack": ["Python"], "github_stars": 1,
            "use_case": "u",
        }]))
        self.stub_search(monkeypatch, {"ai-agents": [
            repo(name="Known", html_url="https://github.com/a/known")]})

        found, skipped = discover.discover(["ai-agents"], min_stars=0, pause=0)
        assert found == []
        assert skipped["known"] == 1

    def test_something_already_queued_is_skipped(self, isolated, monkeypatch):
        """Otherwise every scheduled run re-proposes whatever the reviewer
        has not got to yet."""
        import submissions
        submissions.submit(discover.to_record(repo(name="Queued",
                                                   html_url="https://github.com/a/queued")))
        self.stub_search(monkeypatch, {"ai-agents": [
            repo(name="Queued", html_url="https://github.com/a/queued")]})

        found, skipped = discover.discover(["ai-agents"], min_stars=0, pause=0)
        assert found == []
        assert skipped["known"] == 1

    def test_one_failing_topic_does_not_stop_the_others(self, isolated, monkeypatch):
        self.stub_search(monkeypatch, {
            "ai-agents": discover.SearchFailed("boom"),
            "rag": [repo(name="Survivor", topics=["rag"], html_url="https://github.com/a/s")],
        })
        found, _ = discover.discover(["ai-agents", "rag"], min_stars=0, pause=0)
        assert [r["name"] for r in found] == ["Survivor"]

    def test_every_topic_failing_is_an_error_not_an_empty_result(self, isolated, monkeypatch):
        """The bug this guards: with the network down the crawler reported
        "Nothing new found" and exited 0. On a schedule that reads as a
        healthy, current catalogue while nothing has been checked at all.
        """
        self.stub_search(monkeypatch, {
            "ai-agents": discover.SearchFailed("boom"),
            "rag": discover.SearchFailed("boom"),
        })
        with pytest.raises(discover.SearchFailed, match="none of the 2"):
            discover.discover(["ai-agents", "rag"], min_stars=0, pause=0)

    def test_a_genuinely_empty_result_is_not_an_error(self, isolated, monkeypatch):
        self.stub_search(monkeypatch, {"ai-agents": []})
        found, _ = discover.discover(["ai-agents"], min_stars=0, pause=0)
        assert found == []


class TestTechStackQuality:
    """GitHub's `language` is whatever the repo has most bytes of, which is
    often a packaging artifact rather than a technology."""

    def test_a_packaging_language_is_renamed(self):
        """autoware reports "Dockerfile"; nobody lists that as a stack."""
        record = discover.to_record(repo(language="Dockerfile", topics=["ros2"]))
        assert "Docker" in record["tech_stack"]
        assert "Dockerfile" not in record["tech_stack"]

    @pytest.mark.parametrize("language", ["HTML", "Makefile", "Shell", "Batchfile"])
    def test_build_glue_is_dropped(self, language):
        record = discover.to_record(repo(language=language, topics=["ros2"]))
        assert language not in (record or {}).get("tech_stack", [])

    def test_dropping_it_does_not_lose_the_repository(self):
        """The topics still supply something usable, so a repo that happens
        to be mostly Makefiles is not thrown away."""
        record = discover.to_record(repo(language="Makefile", topics=["ros2"]))
        assert record is not None
        assert record["tech_stack"] == ["ROS 2"]

    def test_a_repository_left_with_nothing_is_skipped(self):
        assert discover.to_record(repo(language="HTML", topics=["ai-agents"])) is None


class TestJsonOutput:
    def test_json_never_queues(self, tmp_path, monkeypatch, capsys):
        """Asking for a listing must not write to the queue as a side effect."""
        monkeypatch.setattr(config, "AGENTS_JSON", tmp_path / "a.json")
        (tmp_path / "a.json").write_text("[]")
        monkeypatch.setattr(config, "SUBMISSIONS_PATH", tmp_path / "q.jsonl")
        monkeypatch.setattr(discover, "search_repos",
                            lambda query, **kw: [repo(html_url="https://github.com/a/b")])

        assert discover.main(["--json", "--topic", "ai-agents", "--min-stars", "0"]) == 0
        assert not (tmp_path / "q.jsonl").exists(), "a listing wrote to the queue"

    def test_the_output_parses_even_when_empty(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(config, "AGENTS_JSON", tmp_path / "a.json")
        (tmp_path / "a.json").write_text("[]")
        monkeypatch.setattr(config, "SUBMISSIONS_PATH", tmp_path / "q.jsonl")
        monkeypatch.setattr(discover, "search_repos", lambda query, **kw: [])

        discover.main(["--json", "--topic", "ai-agents"])
        assert json.loads(capsys.readouterr().out) == []


class TestRateLimits:
    """GitHub's search budget is 10/minute unauthenticated, 30 with a token."""

    def test_an_unauthenticated_run_paces_itself_within_the_budget(self):
        requests_per_minute = 60 / discover.PAUSE_ANONYMOUS
        assert requests_per_minute <= 10

    def test_a_token_allows_a_shorter_pause(self):
        assert discover.PAUSE_WITH_TOKEN < discover.PAUSE_ANONYMOUS
        assert 60 / discover.PAUSE_WITH_TOKEN <= 30

    def test_hitting_the_limit_keeps_what_was_already_found(self, monkeypatch, tmp_path):
        """The run has already spent real API budget. Discarding the results
        means the next run spends it again to learn the same thing."""
        monkeypatch.setattr(config, "AGENTS_JSON", tmp_path / "a.json")
        (tmp_path / "a.json").write_text("[]")
        monkeypatch.setattr(config, "SUBMISSIONS_PATH", tmp_path / "q.jsonl")

        def fake(query, **kwargs):
            if "rag" in query:
                raise discover.RateLimited("out of budget")
            return [repo(name="Found", html_url="https://github.com/a/found")]

        monkeypatch.setattr(discover, "search_repos", fake)
        found, _ = discover.discover(["ai-agents", "rag", "llmops"], min_stars=0, pause=0)

        assert [r["name"] for r in found] == ["Found"]

    def test_being_limited_before_anything_was_searched_says_why(self, monkeypatch, tmp_path):
        """The fix is "set GITHUB_TOKEN". Reporting it as a generic search
        failure drops the one instruction that helps."""
        monkeypatch.setattr(config, "AGENTS_JSON", tmp_path / "a.json")
        (tmp_path / "a.json").write_text("[]")
        monkeypatch.setattr(config, "SUBMISSIONS_PATH", tmp_path / "q.jsonl")
        monkeypatch.setattr(discover, "search_repos",
                            lambda query, **kw: (_ for _ in ()).throw(
                                discover.RateLimited("GitHub rate limit reached; set GITHUB_TOKEN.")))

        with pytest.raises(discover.RateLimited, match="GITHUB_TOKEN"):
            discover.discover(["ai-agents", "rag"], min_stars=0, pause=0)

    def test_the_cli_reports_a_rate_limit_distinctly(self, monkeypatch, tmp_path, caplog):
        monkeypatch.setattr(config, "AGENTS_JSON", tmp_path / "a.json")
        (tmp_path / "a.json").write_text("[]")
        monkeypatch.setattr(config, "SUBMISSIONS_PATH", tmp_path / "q.jsonl")
        monkeypatch.setattr(discover, "search_repos",
                            lambda query, **kw: (_ for _ in ()).throw(
                                discover.RateLimited("GitHub rate limit reached; set GITHUB_TOKEN.")))

        assert discover.main(["--dry-run", "--topic", "rag"]) == 1
        assert "GITHUB_TOKEN" in caplog.text


def test_every_mapped_category_is_reachable_by_a_default_topic():
    """A category in TOPIC_CATEGORIES that no default topic leads to can
    never be proposed by a scheduled run. Three were in that state —
    Automation, Customer Service and Data Analysis — which are the thinnest
    categories in the catalogue, so the gap was costing exactly where it hurt.
    """
    searched = set(discover.DEFAULT_TOPICS)
    mapped = {category for _, category in discover.TOPIC_CATEGORIES}
    reachable = {category for topic, category in discover.TOPIC_CATEGORIES
                 if topic in searched}

    assert mapped == reachable, f"unreachable by any default topic: {sorted(mapped - reachable)}"


def test_the_default_topics_stay_specific_to_ai():
    """"data-analysis" was a default topic for one day and returned pandas,
    superset, metabase, CyberChef and goaccess — good software, none of it
    AI. A topic that mostly returns out-of-scope projects costs a reviewer
    more than it finds.
    """
    assert "data-analysis" not in discover.DEFAULT_TOPICS
    assert {"text-to-sql", "automl"} <= set(discover.DEFAULT_TOPICS)


def test_the_run_stays_inside_the_search_budget():
    """Each added topic is another request; GitHub allows 10 a minute
    unauthenticated."""
    assert 60 / discover.PAUSE_ANONYMOUS <= 10


def test_every_default_topic_is_one_the_catalogue_would_want():
    """A topic is only worth searching if its results belong here.

    "data-analysis" lasted one day and returned pandas, superset, metabase,
    CyberChef and goaccess — good software, none of it AI. The check is that
    each default topic maps to a category *and* that the mapping is not the
    catch-all Framework bucket, which would hide a topic returning anything
    at all.
    """
    by_topic = dict(discover.TOPIC_CATEGORIES)
    unmapped = [t for t in discover.DEFAULT_TOPICS if t not in by_topic]
    assert not unmapped, f"searched but never categorised: {unmapped}"

    # Framework is where a generic agent topic lands; more than a handful of
    # defaults pointing there means the search has lost its focus.
    generic = [t for t in discover.DEFAULT_TOPICS if by_topic[t] == "Framework"]
    assert len(generic) <= 5, f"too many defaults land in Framework: {generic}"


class TestExampleIsNotAlwaysAnExampleRepo:
    """`example` on its own was too broad.

    It rejected ChatterBot, whose description says it "learns replies from
    example conversations" — the word is about the training data, not about
    the repository being a demo. The catalogue is ground truth for "this is a
    tool", so a phrase that refuses one of its entries is the phrase that is
    wrong.
    """

    def test_a_tool_may_mention_example_data(self):
        assert discover.looks_like_a_tool({
            "name": "ChatterBot",
            "description": "A dialog engine that learns replies from example conversations."})

    def test_a_repository_that_is_an_example_is_still_refused(self):
        for description in ["Example project showing how to use the API",
                            "Examples of agent patterns",
                            "Example app built with LangChain"]:
            assert not discover.looks_like_a_tool(
                {"name": "demos", "description": description}), description


class TestAnInterviewCanBeAMethod:
    """`interview` cuts both ways, and the first two attempts each cut wrong.

    Bare, it refused STORM, which researches a topic "by simulating expert
    interviews". A proximity regex over {prep, question, answer, guide,
    handbook, cheat} plus bare "technical|job interview" then refused three
    real tools that *conduct* interviews — a live category — while still
    accepting "practice mock interviews with an LLM".

    What is left matches only phrasings about studying for one. The cases
    below run in both directions on purpose, because a refusal list is only
    half-tested by the things it catches.
    """

    @pytest.mark.parametrize("description", [
        "An AI agent that conducts technical interviews with candidates and scores them.",
        "Automates job interviews end to end for recruiting teams.",
        "Runs customer interviews and turns the answers into a report.",
        "Researches a topic by simulating expert interviews, then writes a cited article.",
        "Records user interviews and transcribes them for product teams.",
    ])
    def test_a_tool_that_conducts_interviews_is_accepted(self, description):
        assert discover.looks_like_a_tool({"name": "x", "description": description})

    @pytest.mark.parametrize("description", [
        "Practice mock interviews with an LLM.",
        "Interview preparation for ML engineers",
        "A deep learning interview question bank",
        "Coding interview questions and answers",
        "Preparing for machine learning interviews",
        "Interview practice with instant feedback",
    ])
    def test_studying_for_an_interview_is_refused(self, description):
        """None of these is caught by the plain phrase list — checked, so the
        cases exercise the pattern they are written for rather than passing
        on `handbook` or `cheat sheet`, which NOT_A_TOOL already holds."""
        assert not discover.NOT_A_TOOL_PATTERN.search(description.lower()), (
            "the phrase list already catches this, so it tests nothing new")
        assert not discover.looks_like_a_tool({"name": "x", "description": description})

    def test_a_prep_repo_can_still_slip_past(self):
        """Recorded rather than fixed. Catching "system design interviews
        explained" needs a bare "system design interview" branch, and that is
        exactly what refused the AI interviewers. One rejection by a reviewer
        beats a category that never reaches one."""
        assert discover.looks_like_a_tool(
            {"name": "x", "description": "System design interviews explained"})


class TestPrepReposNameThemselves:
    """`looks_like_a_tool` searches the repository *name* as well as the
    description, and GitHub names are hyphenated.

    Requiring literal whitespace between the words let `interview-prep`,
    `interview-questions` and `coding-interview-prep` straight through — all
    three refused by the looser pattern that preceded it. The name is checked
    for exactly this reason: a prep repository names itself about as often as
    it describes itself.
    """

    @pytest.mark.parametrize("name", [
        "interview-prep", "interview-questions", "coding-interview-prep",
        "mock-interviews", "interview_prep_2026",
    ])
    def test_a_hyphenated_prep_repo_is_refused(self, name):
        assert not discover.looks_like_a_tool({"name": name, "description": "notes"})

    @pytest.mark.parametrize("name,description", [
        ("interview-prep", "Automated interview preparation with flashcards"),
        ("mock-interview-club", "Run mock interviews and grade yourself"),
        ("coding-interview-prep", "Practice problems and a script to run interview drills"),
        ("x", "Automated mock interviews with instant scoring"),
    ])
    def test_a_verb_does_not_rescue_a_prep_repo(self, name, description):
        """The verb check is allowed to override one phrase, not the filter.

        Written as a short-circuiting `return True`, it re-admitted every one
        of these — "automated interview preparation" is still preparation.
        The earlier cases all passed a bare "notes" description, so none of
        them exercised the override.
        """
        assert not discover.looks_like_a_tool({"name": name, "description": description})


class TestGeneratingQuestionsIsNotStudying:
    """"Interview questions" is the one phrase that cuts both ways: a prep
    repository collects them, a recruiting agent produces them. The verb
    decides."""

    @pytest.mark.parametrize("description", [
        "Generates interview questions from a job description for hiring managers",
        "Writes interview questions tailored to a role",
        "Asks interview questions and scores the answers",
    ])
    def test_a_tool_that_produces_them_is_accepted(self, description):
        assert discover.looks_like_a_tool({"name": "recruiterbot",
                                           "description": description})

    def test_a_collection_of_them_is_still_refused(self):
        assert not discover.looks_like_a_tool(
            {"name": "x", "description": "A deep learning interview question bank"})


class TestEveryVerbStemReachesItsInflection:
    """`score` was written where the other nine alternatives are stems, so
    "scoring interview questions" fell through to the prep filter and was
    refused while "generates interview questions" was accepted."""

    @pytest.mark.parametrize("verb", [
        "Generates", "Creates", "Writes", "Drafts", "Asks",
        "Conducts", "Runs", "Automates", "Scoring", "Transcribes",
    ])
    def test_the_inflected_form_is_recognised(self, verb):
        assert discover.looks_like_a_tool(
            {"name": "x", "description": f"{verb} interview questions for hiring"})
