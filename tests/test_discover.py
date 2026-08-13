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
        assert admin.validate(record, []) == record


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
        assert discover.build_query("rag", 1000) == "topic:rag stars:>=1000"

    def test_a_date_filters_out_abandoned_projects(self):
        query = discover.build_query("rag", 1000, "2026-01-01")
        assert "pushed:>=2026-01-01" in query

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
