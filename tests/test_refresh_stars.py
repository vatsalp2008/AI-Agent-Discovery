import importlib.util

import pytest
from conftest import BACKEND

SCRIPT = BACKEND.parent / "refresh_stars.py"


@pytest.fixture(scope="module")
def refresh():
    spec = importlib.util.spec_from_file_location("_refresh_stars", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("url,expected", [
    ("https://github.com/paul-gauthier/aider", "paul-gauthier/aider"),
    ("http://github.com/OpenBMB/ChatDev", "OpenBMB/ChatDev"),
    ("https://www.github.com/geekan/MetaGPT", "geekan/MetaGPT"),
    ("https://github.com/langchain-ai/langchain/", "langchain-ai/langchain"),
    ("https://github.com/owner/repo.git", "owner/repo"),
    ("https://github.com/owner/repo#readme", "owner/repo"),
    ("https://github.com/owner/repo?tab=stars", "owner/repo"),
])
def test_parses_repository_urls(refresh, url, expected):
    assert refresh.parse_repo(url) == expected


@pytest.mark.parametrize("url", [
    None,
    "",
    "https://cursor.sh",
    "https://n8n.io",
    "https://zapier.com/ai",
    "https://gitlab.com/owner/repo",
    "https://github.com/features/copilot",   # a product page, not a repo
    "https://github.com/orgs/anthropics",
])
def test_ignores_non_repository_urls(refresh, url):
    assert refresh.parse_repo(url) is None


def test_plans_only_changed_counts(refresh):
    records = [
        {"name": "A", "url": "https://github.com/o/a", "github_stars": 100},
        {"name": "B", "url": "https://github.com/o/b", "github_stars": 200},
        {"name": "C", "url": "https://example.com", "github_stars": 5},
    ]
    changes = refresh.plan_updates(records, {"o/a": 150, "o/b": 200})
    assert [(c[0]["name"], c[1], c[2]) for c in changes] == [("A", 100, 150)]


def test_plan_skips_repos_that_could_not_be_fetched(refresh):
    records = [{"name": "A", "url": "https://github.com/o/a", "github_stars": 100}]
    assert refresh.plan_updates(records, {"o/a": None}) == []


def test_plan_handles_a_missing_star_field(refresh):
    records = [{"name": "A", "url": "https://github.com/o/a"}]
    changes = refresh.plan_updates(records, {"o/a": 42})
    assert changes[0][1:] == (0, 42)


def test_plan_detects_decreases(refresh):
    records = [{"name": "A", "url": "https://github.com/o/a", "github_stars": 500}]
    assert refresh.plan_updates(records, {"o/a": 400})[0][1:] == (500, 400)


def test_format_change_shows_direction(refresh):
    record = {"name": "Aider"}
    assert "↑" in refresh.format_change(record, 100, 200)
    assert "↓" in refresh.format_change(record, 200, 100)


def test_fetch_stars_reports_failure_without_raising(refresh, monkeypatch):
    import urllib.error

    def boom(*a, **k):
        raise urllib.error.URLError("no network")

    monkeypatch.setattr(refresh.urllib.request, "urlopen", boom)
    assert refresh.fetch_stars("o/a") is None


def test_fetch_stars_parses_the_count(refresh, monkeypatch):
    import contextlib
    import io

    @contextlib.contextmanager
    def fake_urlopen(request, timeout=None):
        yield io.BytesIO(b'{"stargazers_count": 1234}')

    monkeypatch.setattr(refresh.urllib.request, "urlopen", fake_urlopen)
    assert refresh.fetch_stars("o/a") == 1234


def test_token_is_sent_when_provided(refresh, monkeypatch):
    import contextlib
    import io

    captured = {}

    @contextlib.contextmanager
    def fake_urlopen(request, timeout=None):
        captured["auth"] = request.headers.get("Authorization")
        yield io.BytesIO(b'{"stargazers_count": 1}')

    monkeypatch.setattr(refresh.urllib.request, "urlopen", fake_urlopen)
    refresh.fetch_stars("o/a", token="secret")
    assert captured["auth"] == "Bearer secret"


def test_dry_run_leaves_the_file_untouched(refresh, agents_json, monkeypatch):
    monkeypatch.setattr(refresh, "fetch_stars", lambda repo, token=None: 999999)
    before = agents_json.read_text()
    assert refresh.main(["--dry-run"]) == 0
    assert agents_json.read_text() == before


def test_writes_updated_counts(refresh, agents_json, monkeypatch):
    import json

    monkeypatch.setattr(refresh, "fetch_stars", lambda repo, token=None: 999999)
    assert refresh.main([]) == 0

    updated = {r["name"]: r["github_stars"] for r in json.loads(agents_json.read_text())}
    # Only the two agents with GitHub repo URLs should change.
    assert updated["Aider"] == 999999
    assert updated["GPT Researcher"] == 999999
    assert updated["Cursor"] == 35000  # https://cursor.sh, not a repo


def test_total_fetch_failure_is_not_reported_as_up_to_date(refresh, agents_json, monkeypatch, caplog):
    """A network outage must not look like "everything is current"."""
    monkeypatch.setattr(refresh, "fetch_stars", lambda repo, token=None: None)
    assert refresh.main(["--dry-run"]) == 1
    assert "unverified" in caplog.text
    assert "up to date" not in caplog.text


def test_partial_failure_still_applies_what_was_fetched(refresh, agents_json, monkeypatch):
    import json

    monkeypatch.setattr(
        refresh, "fetch_stars",
        lambda repo, token=None: 777 if repo == "paul-gauthier/aider" else None,
    )
    assert refresh.main([]) == 0
    updated = {r["name"]: r["github_stars"] for r in json.loads(agents_json.read_text())}
    assert updated["Aider"] == 777
    assert updated["GPT Researcher"] == 14000  # unchanged, could not be fetched
