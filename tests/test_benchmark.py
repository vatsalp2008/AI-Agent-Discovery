"""The benchmark's reporting logic, without needing a real index."""

import importlib.util
import json

import pytest
from conftest import BACKEND

BENCH_PATH = BACKEND.parent / "benchmark.py"


@pytest.fixture(scope="module")
def bench():
    spec = importlib.util.spec_from_file_location("_benchmark", BENCH_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_summarize_reports_median_and_p90(bench):
    stats = bench.summarize([10, 20, 30, 40, 50])
    assert stats["runs"] == 5
    assert stats["median_ms"] == 30
    assert stats["max_ms"] == 50
    assert stats["p90_ms"] >= stats["median_ms"]


def test_summarize_handles_a_single_sample(bench):
    stats = bench.summarize([7])
    assert stats["median_ms"] == stats["p90_ms"] == stats["max_ms"] == 7


def test_timed_runs_the_requested_number_of_samples(bench):
    seen = []
    samples = bench.timed(lambda i: seen.append(i), 5)
    assert seen == [0, 1, 2, 3, 4]
    assert len(samples) == 5


def test_render_includes_every_operation(bench):
    output = bench.render({
        "search_uncached": {"runs": 5, "median_ms": 14.5, "p90_ms": 19.0},
        "_meta": {"agents": 60, "embedding_model": "nomic-embed-text"},
    })
    assert "search_uncached" in output
    assert "60 agents" in output
    assert "_meta" not in output


def test_compare_flags_a_slowdown(bench):
    output = bench.compare(
        {"search": {"runs": 5, "median_ms": 30.0}},
        {"search": {"runs": 5, "median_ms": 10.0}},
    )
    assert "+200.0%" in output
    assert "slower" in output


def test_compare_flags_an_improvement(bench):
    output = bench.compare(
        {"search": {"runs": 5, "median_ms": 5.0}},
        {"search": {"runs": 5, "median_ms": 10.0}},
    )
    assert "faster" in output


def test_compare_ignores_operations_missing_from_the_baseline(bench):
    output = bench.compare(
        {"new_op": {"runs": 1, "median_ms": 1.0}},
        {"old_op": {"runs": 1, "median_ms": 1.0}},
    )
    assert "new_op" not in output


def test_compare_survives_a_zero_baseline(bench):
    """Cached lookups can legitimately round to 0ms."""
    output = bench.compare(
        {"cached": {"runs": 1, "median_ms": 0.0}},
        {"cached": {"runs": 1, "median_ms": 0.0}},
    )
    assert "cached" not in output  # skipped rather than dividing by zero


def test_json_output_round_trips(bench, tmp_path):
    payload = {"search": {"runs": 1, "median_ms": 1.0}}
    path = tmp_path / "run.json"
    path.write_text(json.dumps(payload))
    assert json.loads(path.read_text()) == payload


def test_scaled_catalogue_reaches_the_target(bench, monkeypatch, tmp_path):
    """Synthetic agents reuse real descriptions so embeddings stay realistic."""
    import json

    import config

    catalogue = tmp_path / "agents.json"
    catalogue.write_text(json.dumps([
        {"name": "A", "description": "d", "category": "c", "tech_stack": [], "github_stars": 0,
         "url": "", "use_case": ""},
        {"name": "B", "description": "e", "category": "c", "tech_stack": [], "github_stars": 0,
         "url": "", "use_case": ""},
    ]))
    monkeypatch.setattr(config, "AGENTS_JSON", catalogue)

    scaled = bench.scaled_catalogue(7)
    assert len(scaled) == 7
    assert len({r["name"] for r in scaled}) == 7, "names must stay unique"
    assert scaled[0]["name"] == "A", "the first copy keeps the real names"
    assert scaled[0]["description"] == "d", "descriptions are reused, not invented"


def test_scaled_catalogue_refuses_an_empty_source(bench, monkeypatch, tmp_path):
    import json

    import config

    catalogue = tmp_path / "agents.json"
    catalogue.write_text(json.dumps([]))
    monkeypatch.setattr(config, "AGENTS_JSON", catalogue)

    with pytest.raises(SystemExit):
        bench.scaled_catalogue(5)
