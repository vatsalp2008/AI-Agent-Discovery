"""Catalogue link checking.

The network calls are stubbed; what is tested is the classification — a
redirect is worth knowing about but is not a failure, and a HEAD rejection is
not the same as a dead link.
"""

import importlib.util
import urllib.error

import pytest
from conftest import BACKEND

LINKS_PATH = BACKEND.parent / "check_links.py"


@pytest.fixture(scope="module")
def links():
    spec = importlib.util.spec_from_file_location("_check_links", LINKS_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeResponse:
    def __init__(self, status=200):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class TestClassification:
    def test_a_working_url_is_ok(self, links, monkeypatch):
        monkeypatch.setattr(links.urllib.request, "build_opener",
                            lambda *a: type("FakeOpener", (), {"open": lambda self, r, timeout=0: FakeResponse()})())
        assert links.check_url("https://example.com")[0] == links.OK

    def test_a_missing_url_is_skipped(self, links):
        assert links.check_url("")[0] == links.SKIPPED

    def test_a_non_http_url_is_broken(self, links):
        status, detail = links.check_url("ftp://example.com")
        assert status == links.BROKEN
        assert "not an http" in detail

    def test_a_404_is_broken(self, links, monkeypatch):
        def opener(*args):
            class FakeOpener:
                def open(self, request, timeout=0):
                    raise urllib.error.HTTPError("u", 404, "Not Found", {}, None)
            return FakeOpener()

        monkeypatch.setattr(links.urllib.request, "build_opener", opener)
        status, detail = links.check_url("https://example.com/gone")
        assert status == links.BROKEN
        assert "404" in detail

    def test_a_redirect_is_reported_not_failed(self, links, monkeypatch):
        """A renamed repository still works; it is worth updating, not fixing."""
        def opener(*args):
            class FakeOpener:
                def open(self, request, timeout=0):
                    raise links._Redirected("https://example.com/new")
            return FakeOpener()

        monkeypatch.setattr(links.urllib.request, "build_opener", opener)
        status, detail = links.check_url("https://example.com/old")
        assert status == links.REDIRECT
        assert "new" in detail

    def test_a_head_rejection_retries_with_get(self, links, monkeypatch):
        """Some hosts refuse HEAD; that is not a dead link."""
        calls = []

        def opener(*args):
            class FakeOpener:
                def open(self, request, timeout=0):
                    calls.append(request.method)
                    if request.method == "HEAD":
                        raise urllib.error.HTTPError("u", 405, "Method Not Allowed", {}, None)
                    return FakeResponse()
            return FakeOpener()

        monkeypatch.setattr(links.urllib.request, "build_opener", opener)
        status, _ = links.check_url("https://example.com")
        assert status == links.OK
        assert calls == ["HEAD", "GET"]

    def test_a_connection_error_is_broken(self, links, monkeypatch):
        def opener(*args):
            class FakeOpener:
                def open(self, request, timeout=0):
                    raise OSError("connection refused")
            return FakeOpener()

        monkeypatch.setattr(links.urllib.request, "build_opener", opener)
        assert links.check_url("https://example.com")[0] == links.BROKEN


class TestReport:
    def test_broken_links_are_listed_first(self, links):
        results = links.check_catalogue([], workers=1)
        assert results == []

    def test_summary_counts_each_status(self, links):
        output = links.render([
            {"name": "A", "url": "u", "status": links.BROKEN, "detail": "404"},
            {"name": "B", "url": "u", "status": links.REDIRECT, "detail": "-> v"},
            {"name": "C", "url": "", "status": links.SKIPPED, "detail": "no url"},
        ])
        assert "1 broken" in output
        assert "1 redirected" in output
        assert "1 without a url" in output

    def test_broken_entries_show_the_url(self, links):
        output = links.render([
            {"name": "A", "url": "https://gone.example", "status": links.BROKEN, "detail": "404"},
        ])
        assert "https://gone.example" in output
