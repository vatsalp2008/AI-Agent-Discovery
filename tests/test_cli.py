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
