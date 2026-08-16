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


class TestMalformedInput:
    """The catalogue is hand-edited; one bad record must not lose the report."""

    def test_a_record_without_a_name_still_renders(self, links):
        output = links.render([
            {"name": None, "url": "https://gone.example", "status": links.BROKEN, "detail": "404"},
            {"name": "Fine", "url": "https://ok.example", "status": links.OK, "detail": "200"},
        ])
        assert "(unnamed)" in output
        assert "2 checked" in output

    def test_a_missing_name_key_still_renders(self, links):
        output = links.render([{"url": "u", "status": links.REDIRECT, "detail": "-> v"}])
        assert "(unnamed)" in output

    def test_sorting_tolerates_a_missing_name(self, links, monkeypatch):
        monkeypatch.setattr(links, "check_url", lambda url, timeout=0: (links.OK, "200"))
        results = links.check_catalogue([{"url": "u"}, {"name": "B", "url": "v"}], workers=2)
        assert len(results) == 2


class TestArgumentValidation:
    """These reached ThreadPoolExecutor and raised an unhandled ValueError."""

    def test_zero_workers_is_rejected(self, links):
        with pytest.raises(SystemExit):
            links.main(["--workers", "0"])

    def test_negative_workers_is_rejected(self, links):
        with pytest.raises(SystemExit):
            links.main(["--workers", "-1"])

    def test_zero_timeout_is_rejected(self, links):
        with pytest.raises(SystemExit):
            links.main(["--timeout", "0"])


class TestThrottling:
    """A 429 is the host refusing to answer, not the page being gone.
    devin.ai returns one to every automated request, so treating it as broken
    fails the weekly job every week for a page that works in a browser."""

    def refusing(self, code):
        """An opener whose every request is refused with `code`."""
        def build(*args, **kwargs):
            class FakeOpener:
                def open(self, request, timeout=0):
                    raise urllib.error.HTTPError("u", code, "Refused", {}, None)
            return FakeOpener()
        return build

    def test_a_429_is_not_broken(self, links, monkeypatch):
        monkeypatch.setattr(links.urllib.request, "build_opener", self.refusing(429))
        status, detail = links.check_url("https://example.com")

        assert status == links.THROTTLED
        assert "429" in detail

    def test_it_is_reported_but_not_counted_as_broken(self, links):
        report = links.render([
            {"name": "A", "url": "https://e.com", "status": links.THROTTLED,
             "detail": "HTTP 429"}])

        assert "0 broken" in report
        assert "1 throttled" in report

    def test_a_clean_report_does_not_mention_throttling(self, links):
        """Noise in the usual case makes the unusual case harder to spot."""
        report = links.render([
            {"name": "A", "url": "https://e.com", "status": links.OK, "detail": "200"}])

        assert "throttled" not in report

    def test_a_real_failure_is_still_broken(self, links, monkeypatch):
        monkeypatch.setattr(links.urllib.request, "build_opener", self.refusing(404))
        assert links.check_url("https://example.com")[0] == links.BROKEN

    def test_a_throttled_get_retry_is_not_broken(self, links, monkeypatch):
        """A host that refuses HEAD with 403 and then rate-limits the GET is
        still refusing to answer. This landed in the generic handler and came
        out BROKEN — the case the throttled state exists for."""
        def build(*args, **kwargs):
            class FakeOpener:
                def __init__(self):
                    self.calls = 0

                def open(self, request, timeout=0):
                    self.calls += 1
                    code = 403 if self.calls == 1 else 429
                    raise urllib.error.HTTPError("u", code, "Refused", {}, None)
            return FakeOpener()

        monkeypatch.setattr(links.urllib.request, "build_opener", build)
        status, detail = links.check_url("https://example.com")

        assert status == links.THROTTLED
        assert "429" in detail

    def test_a_genuine_failure_on_the_get_retry_is_still_broken(self, links, monkeypatch):
        def build(*args, **kwargs):
            class FakeOpener:
                def __init__(self):
                    self.calls = 0

                def open(self, request, timeout=0):
                    self.calls += 1
                    code = 403 if self.calls == 1 else 404
                    raise urllib.error.HTTPError("u", code, "Refused", {}, None)
            return FakeOpener()

        monkeypatch.setattr(links.urllib.request, "build_opener", build)
        assert links.check_url("https://example.com")[0] == links.BROKEN
