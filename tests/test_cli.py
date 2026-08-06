import importlib.util

import pytest
from conftest import BACKEND

CLI_PATH = BACKEND.parent / "cli.py"


@pytest.fixture(scope="module")
def cli():
    spec = importlib.util.spec_from_file_location("_cli", CLI_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parser_defaults(cli):
    import config

    args = cli.build_parser().parse_args(["find me an agent"])
    assert args.query == "find me an agent"
    assert args.limit == config.SEARCH_DEFAULT_LIMIT
    assert args.category is None


def test_parser_accepts_filters(cli):
    args = cli.build_parser().parse_args(["chatbot", "-n", "3", "-c", "Customer Service"])
    assert (args.limit, args.category) == (3, "Customer Service")


@pytest.mark.parametrize("stars,expected", [(0, "0"), (None, "0"), (999, "999"), (35000, "35.0k")])
def test_format_stars(cli, stars, expected):
    assert cli.format_stars(stars) == expected


def test_format_results_renders_score_and_metadata(cli):
    output = cli.format_results([{
        "name": "Cursor",
        "score": 0.91,
        "metadata": {
            "category": "Code Generation",
            "stars": 35000,
            "description": "AI code editor.",
            "url": "https://cursor.sh",
        },
    }])
    assert "1. Cursor" in output
    assert "91% match" in output
    assert "Code Generation" in output
    assert "35.0k stars" in output
    assert "https://cursor.sh" in output


def test_format_results_handles_no_matches(cli):
    assert cli.format_results([]) == "No matching agents found."


def test_format_results_tolerates_missing_fields(cli):
    assert "Unknown" in cli.format_results([{"metadata": {}}])


def test_format_stats(cli):
    output = cli.format_stats({
        "count": 21,
        "categories": 8,
        "top_category": {"name": "Code Generation", "count": 6},
        "total_stars": 653000,
        "embedding_model": "nomic-embed-text",
    })
    assert "21" in output
    assert "Code Generation (6)" in output
    assert "653,000" in output


def test_format_stats_handles_an_empty_index(cli):
    assert "N/A" in cli.format_stats({"count": 0, "top_category": None})


def test_no_arguments_prints_help_and_exits_nonzero(cli, capsys):
    assert cli.main([]) == 2
    assert "usage" in capsys.readouterr().out.lower()


def test_json_flag_is_parsed(cli):
    args = cli.build_parser().parse_args(["query", "--json"])
    assert args.as_json is True
    assert cli.build_parser().parse_args(["query"]).as_json is False


def test_summarize_flag_is_parsed(cli):
    assert cli.build_parser().parse_args(["query", "--summarize"]).summarize is True
    assert cli.build_parser().parse_args(["query"]).summarize is False


def test_json_output_is_machine_readable(cli, capsys, monkeypatch):
    import json

    class FakeStore:
        vector_store = object()
        stale_model = None

        def search(self, query, limit=None, category=None, min_score=None):
            return [{"name": "Cursor", "score": 0.9, "metadata": {"category": "Code Generation"}}]

    monkeypatch.setattr(cli, "_build_store", lambda: FakeStore())
    assert cli.main(["code editor", "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["query"] == "code editor"
    assert payload["results"][0]["name"] == "Cursor"
    assert payload["summary"] is None


def test_json_stats_output(cli, capsys, monkeypatch):
    import json

    class FakeStore:
        vector_store = object()
        stale_model = None

        def get_stats(self):
            return {"count": 37, "categories": 8}

    monkeypatch.setattr(cli, "_build_store", lambda: FakeStore())
    assert cli.main(["--stats", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["count"] == 37


def _agent(name, category="Code Generation", stars=100, stack="Python"):
    return {"name": name, "metadata": {"name": name, "category": category, "stars": stars, "stack": stack}}


class TestSortingAndFiltering:
    AGENTS = [
        _agent("Zebra", "Research", 500, "Python,LangChain"),
        _agent("alpha", "Code Generation", 100, "TypeScript"),
        _agent("Mid", "Code Generation", 300, "Python"),
    ]

    def test_sort_by_name_is_case_insensitive(self, cli):
        assert [a["name"] for a in cli.sort_agents(self.AGENTS, "name")] == ["alpha", "Mid", "Zebra"]

    def test_sort_by_stars_defaults_to_descending(self, cli):
        assert [a["name"] for a in cli.sort_agents(self.AGENTS, "stars")] == ["Zebra", "Mid", "alpha"]

    def test_sort_direction_can_be_overridden(self, cli):
        assert [a["name"] for a in cli.sort_agents(self.AGENTS, "stars", "asc")] == ["alpha", "Mid", "Zebra"]

    def test_sort_by_category_breaks_ties_by_name(self, cli):
        assert [a["name"] for a in cli.sort_agents(self.AGENTS, "category")] == ["alpha", "Mid", "Zebra"]

    def test_filter_by_category(self, cli):
        got = cli.filter_agents(self.AGENTS, category="Research")
        assert [a["name"] for a in got] == ["Zebra"]

    def test_filter_by_category_is_case_insensitive(self, cli):
        assert len(cli.filter_agents(self.AGENTS, category="research")) == 1

    def test_filter_by_tech(self, cli):
        got = cli.filter_agents(self.AGENTS, tech="Python")
        assert sorted(a["name"] for a in got) == ["Mid", "Zebra"]

    def test_filter_by_tech_matches_whole_entries(self, cli):
        """'Lang' must not match the 'LangChain' entry."""
        assert cli.filter_agents(self.AGENTS, tech="Lang") == []
        assert len(cli.filter_agents(self.AGENTS, tech="LangChain")) == 1

    def test_filters_combine(self, cli):
        got = cli.filter_agents(self.AGENTS, category="Code Generation", tech="Python")
        assert [a["name"] for a in got] == ["Mid"]

    def test_no_filters_returns_everything(self, cli):
        assert len(cli.filter_agents(self.AGENTS)) == 3


def test_new_flags_are_parsed(cli):
    args = cli.build_parser().parse_args(
        ["q", "--tech", "Python", "--sort", "stars", "--order", "asc", "--min-score", "0.4"]
    )
    assert args.tech == "Python"
    assert args.sort == "stars"
    assert args.order == "asc"
    assert args.min_score == 0.4


def test_min_score_is_passed_through_to_the_store(cli, monkeypatch):
    seen = {}

    class FakeStore:
        vector_store = object()
        stale_model = None

        def search(self, query, limit=None, category=None, min_score=None):
            seen["min_score"] = min_score
            return []

    monkeypatch.setattr(cli, "_build_store", lambda: FakeStore())
    cli.main(["anything", "--min-score", "0.7"])
    assert seen["min_score"] == 0.7


def test_tech_list_prints_counts(cli, capsys, monkeypatch):
    class FakeStore:
        vector_store = object()
        stale_model = None

        def get_tech_stacks(self):
            return [{"name": "Python", "count": 26}, {"name": "TypeScript", "count": 10}]

    monkeypatch.setattr(cli, "_build_store", lambda: FakeStore())
    assert cli.main(["--tech-list"]) == 0

    out = capsys.readouterr().out
    assert "Python" in out and "26" in out


def test_listing_with_no_matches_exits_nonzero(cli, capsys, monkeypatch):
    class FakeStore:
        vector_store = object()
        stale_model = None

        def get_all_agents(self):
            return [_agent("Only", "Research")]

    monkeypatch.setattr(cli, "_build_store", lambda: FakeStore())
    assert cli.main(["--list", "--category", "Nonexistent"]) == 1
    assert "No matching agents" in capsys.readouterr().err
