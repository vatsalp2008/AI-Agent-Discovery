"""Auditing catalogue entries that have gone stale.

Runs against fixture payloads rather than the network. The judgement being
tested is what counts as *worth a maintainer's attention* — a report that
flags a third of the catalogue for things nobody would act on is a report
nobody reads.
"""

import json
import sys
from datetime import datetime, timedelta, timezone

import pytest

import config

sys.path.insert(0, str(config.PACKAGE_DIR))

import audit  # noqa: E402


def entry(**overrides):
    """A catalogue record."""
    base = {
        "name": "SomeAgent",
        "description": "An agent that does a useful and well described thing.",
        "category": "Framework",
        "tech_stack": ["Python", "PyTorch"],
        "github_stars": 4200,
        "url": "https://github.com/acme/someagent",
        "use_case": "Building an agent",
    }
    base.update(overrides)
    return base


def payload(**overrides):
    """A GitHub repository, healthy unless told otherwise."""
    base = {
        "full_name": "acme/someagent",
        "archived": False,
        "language": "Python",
        "pushed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    base.update(overrides)
    return base


def months_ago(n):
    when = datetime.now(timezone.utc) - timedelta(days=31 * n)
    return when.isoformat().replace("+00:00", "Z")


def kinds(record, data, **kwargs):
    return [issue["kind"] for issue in audit.find_issues(record, data, **kwargs)]


class TestAHealthyEntry:
    def test_says_nothing(self):
        assert audit.find_issues(entry(), payload()) == []

    def test_a_stack_that_lists_the_language_is_fine(self):
        assert kinds(entry(tech_stack=["Python"]), payload(language="Python")) == []

    def test_the_match_ignores_case(self):
        assert kinds(entry(tech_stack=["python"]), payload(language="Python")) == []

    def test_a_richer_stack_than_the_language_is_fine(self):
        """Stacks are curated and deliberately say more than one word."""
        assert kinds(entry(tech_stack=["Python", "PyTorch", "CUDA"]),
                     payload(language="Python")) == []


class TestWhatIsWorthReporting:
    def test_an_archived_repository(self):
        assert "archived" in kinds(entry(), payload(archived=True))

    def test_a_repository_that_moved(self):
        """The API answers on the old path after a rename, so this is where
        the new name shows up without following a redirect."""
        issues = audit.find_issues(entry(), payload(full_name="newowner/someagent"))
        moved = [i for i in issues if i["kind"] == "moved"]
        assert moved and "newowner/someagent" in moved[0]["detail"]

    def test_a_repository_that_disappeared(self):
        assert kinds(entry(), None) == ["missing"]

    def test_a_dormant_repository(self):
        assert "dormant" in kinds(entry(), payload(pushed_at=months_ago(24)))

    def test_a_recently_pushed_one_is_not_dormant(self):
        assert "dormant" not in kinds(entry(), payload(pushed_at=months_ago(2)))

    def test_the_dormancy_threshold_is_configurable(self):
        data = payload(pushed_at=months_ago(12))
        assert "dormant" not in kinds(entry(), data, stale_months=18)
        assert "dormant" in kinds(entry(), data, stale_months=6)

    def test_a_language_the_entry_does_not_list(self):
        assert "stack" in kinds(entry(tech_stack=["Python"]), payload(language="Rust"))

    def test_several_problems_are_all_reported(self):
        """A project that is both archived and dormant should say both;
        reporting one hides the other until it is fixed."""
        issues = kinds(entry(), payload(archived=True, pushed_at=months_ago(30)))
        assert set(issues) >= {"archived", "dormant"}


class TestWhatIsNotWorthReporting:
    @pytest.mark.parametrize("language", [
        "Jupyter Notebook", "Dockerfile", "Makefile", "HTML", "Shell", "TeX", "CMake",
    ])
    def test_a_format_language_is_not_a_stack_finding(self, language):
        """GitHub reports whichever language has the most bytes, so an ML
        project ships as "Jupyter Notebook". Ten of the first eighteen stack
        findings were that, against entries correctly saying Python and
        PyTorch — noise that would have buried nine real archived projects.
        """
        assert "stack" not in kinds(entry(tech_stack=["Python"]), payload(language=language))

    def test_a_repository_with_no_language_is_not_flagged(self):
        assert "stack" not in kinds(entry(), payload(language=None))

    def test_an_unparsable_push_date_is_not_dormancy(self):
        """Unknown is not old."""
        assert "dormant" not in kinds(entry(), payload(pushed_at="not a date"))
        assert "dormant" not in kinds(entry(), payload(pushed_at=None))

    def test_an_entry_with_no_github_url_is_skipped_entirely(self):
        findings, skipped, checked = audit.audit([entry(url="https://example.com")])
        assert findings == [] and skipped == [] and checked == set()


class TestTheRun:
    def stub(self, monkeypatch, by_repo):
        def fake(repo, **kwargs):
            outcome = by_repo.get(repo)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        monkeypatch.setattr(audit, "fetch_repo", fake)

    def test_reports_only_what_has_a_problem(self, monkeypatch):
        self.stub(monkeypatch, {
            "acme/good": payload(full_name="acme/good"),
            "acme/bad": payload(full_name="acme/bad", archived=True),
        })
        records = [entry(name="Good", url="https://github.com/acme/good"),
                   entry(name="Bad", url="https://github.com/acme/bad")]

        findings, _, checked = audit.audit(records)
        assert [f["name"] for f in findings] == ["Bad"]
        assert checked == {"Good", "Bad"}

    def test_one_unreachable_repository_does_not_stop_the_rest(self, monkeypatch):
        self.stub(monkeypatch, {
            "acme/down": audit.Unavailable("HTTP 500"),
            "acme/bad": payload(full_name="acme/bad", archived=True),
        })
        records = [entry(name="Down", url="https://github.com/acme/down"),
                   entry(name="Bad", url="https://github.com/acme/bad")]

        findings, skipped, checked = audit.audit(records)
        assert [f["name"] for f in findings] == ["Bad"]
        assert [name for name, _ in skipped] == ["Down"]
        assert checked == {"Bad"}, "an unreachable entry was counted as checked"

    def test_everything_unreachable_is_an_error_not_a_clean_report(self, monkeypatch, capsys):
        """"Nothing is stale" and "nothing could be checked" are opposite
        outcomes, and on a schedule the second must not read as the first."""
        self.stub(monkeypatch, {"acme/a": audit.Unavailable("rate limited")})
        records = [entry(name="A", url="https://github.com/acme/a")]

        monkeypatch.setattr(config, "AGENTS_JSON", _write(records))
        assert audit.main([]) == 1

    def test_a_clean_catalogue_exits_zero_even_with_fail_on_findings(self, monkeypatch):
        self.stub(monkeypatch, {"acme/a": payload(full_name="acme/a")})
        monkeypatch.setattr(config, "AGENTS_JSON",
                            _write([entry(name="A", url="https://github.com/acme/a")]))

        assert audit.main(["--fail-on-findings"]) == 0

    def test_findings_can_fail_the_run(self, monkeypatch):
        self.stub(monkeypatch, {"acme/a": payload(full_name="acme/a", archived=True)})
        monkeypatch.setattr(config, "AGENTS_JSON",
                            _write([entry(name="A", url="https://github.com/acme/a")]))

        assert audit.main(["--fail-on-findings"]) == 1
        assert audit.main([]) == 0, "findings alone should not fail the run"

    def test_json_output_parses_even_with_nothing_to_report(self, monkeypatch, capsys):
        self.stub(monkeypatch, {"acme/a": payload(full_name="acme/a")})
        monkeypatch.setattr(config, "AGENTS_JSON",
                            _write([entry(name="A", url="https://github.com/acme/a")]))

        audit.main(["--json"])
        assert json.loads(capsys.readouterr().out) == []


_TMP = []


def _write(records):
    """A throwaway agents.json holding `records`."""
    import tempfile
    from pathlib import Path

    path = Path(tempfile.mkdtemp()) / "agents.json"
    path.write_text(json.dumps(records))
    _TMP.append(path)
    return path


class TestApplyingStatus:
    def finding(self, name, *kinds):
        return {"name": name, "url": "https://github.com/a/b",
                "issues": [{"kind": k, "detail": ""} for k in kinds]}

    def test_archived_beats_dormant(self):
        """An archived project is not merely quiet; a repository that is both
        should say the stronger thing."""
        wanted = audit.statuses_for([self.finding("A", "dormant", "archived")])
        assert wanted == {"A": "archived"}

    def test_only_health_findings_become_a_status(self):
        """A moved or mis-stacked entry wants a human to decide what it
        should say instead — neither is a flag to flip."""
        wanted = audit.statuses_for([self.finding("A", "moved", "stack")])
        assert wanted == {}

    def test_a_missing_repository_keeps_the_status_it_had(self):
        """Clearing it would quietly upgrade a deleted project to healthy —
        the wrong direction for the finding that most needs a human."""
        records = [entry(name="A", status="archived")]
        wanted = audit.statuses_for([self.finding("A", "missing")], records)

        assert wanted == {"A": "archived"}

    def test_a_missing_repository_with_no_status_stays_active(self):
        assert audit.statuses_for([self.finding("A", "missing")], [entry(name="A")]) == {
            "A": "active"}

    def test_an_entry_the_audit_never_checked_is_left_alone(self):
        """Entries hosted outside GitHub are never examined; defaulting them
        to active would clear a warning nobody re-verified."""
        records = [entry(name="Elsewhere", status="archived")]
        assert audit.apply_statuses(records, {}, checked=set()) == []
        assert records[0]["status"] == "archived"

    def test_it_sets_the_status(self):
        records = [entry(name="A")]
        changes = audit.apply_statuses(records, {"A": "archived"})

        assert records[0]["status"] == "archived"
        assert changes == [("A", "active", "archived")]

    def test_it_clears_a_status_that_no_longer_applies(self):
        """Archived repositories get unarchived. Leaving the warning would
        make the catalogue wrong in the other direction."""
        records = [entry(name="A", status="archived")]
        changes = audit.apply_statuses(records, {})

        assert "status" not in records[0]
        assert changes == [("A", "archived", "active")]

    def test_an_unchanged_entry_is_left_alone(self):
        records = [entry(name="A", status="archived")]
        assert audit.apply_statuses(records, {"A": "archived"}) == []

    def test_it_refuses_to_write_when_something_could_not_be_checked(self, monkeypatch):
        """An unchecked entry looks "not flagged", so writing would clear a
        real warning on a repository nobody actually looked at."""
        def fake(repo, **kwargs):
            if repo == "acme/down":
                raise audit.Unavailable("HTTP 500")
            return payload(full_name=repo, archived=True)

        monkeypatch.setattr(audit, "fetch_repo", fake)
        path = _write([entry(name="Down", url="https://github.com/acme/down"),
                       entry(name="Bad", url="https://github.com/acme/bad")])
        monkeypatch.setattr(config, "AGENTS_JSON", path)

        assert audit.main(["--apply-status"]) == 1
        assert "status" not in json.loads(path.read_text())[1]


def test_applying_statuses_writes_atomically(monkeypatch, tmp_path):
    """An interrupted CI step must not leave a truncated catalogue. Every
    other writer of this file uses tmp + replace."""
    records = [entry(name="A", url="https://github.com/acme/a")]
    path = _write(records)
    monkeypatch.setattr(config, "AGENTS_JSON", path)
    monkeypatch.setattr(audit, "fetch_repo",
                        lambda repo, **kw: payload(full_name="acme/a", archived=True))

    replaced = []
    real = audit.os.replace
    monkeypatch.setattr(audit.os, "replace",
                        lambda src, dst: (replaced.append((src, dst)), real(src, dst))[1])

    assert audit.main(["--apply-status"]) == 0
    assert replaced, "the catalogue was written in place rather than swapped"
    assert json.loads(path.read_text())[0]["status"] == "archived"


class TestFollowingRenames:
    """Projects get renamed constantly — 21 in one run on 08-10, 2 on 08-14.
    The audit already knows the new path; acting on it is a rewrite of one
    substring, and getting it wrong points the catalogue at nothing."""

    def moved(self, name, to):
        return {"name": name, "url": "", "issues": [{"kind": "moved", "to": to,
                                                     "detail": ""}]}

    def test_it_rewrites_the_repository_path(self):
        records = [entry(name="A", url="https://github.com/old/repo")]
        changes = audit.follow_moves(records, [self.moved("A", "new/repo")])

        assert records[0]["url"] == "https://github.com/new/repo"
        assert changes == [("A", "https://github.com/old/repo",
                            "https://github.com/new/repo")]

    def test_it_leaves_the_rest_of_the_url_alone(self):
        """The finding is about the repository, not the whole link."""
        records = [entry(name="A", url="https://github.com/old/repo/tree/main/docs")]
        audit.follow_moves(records, [self.moved("A", "new/repo")])

        assert records[0]["url"] == "https://github.com/new/repo/tree/main/docs"

    def test_an_entry_hosted_elsewhere_is_untouched(self):
        records = [entry(name="A", url="https://example.com/thing")]
        assert audit.follow_moves(records, [self.moved("A", "new/repo")]) == []
        assert records[0]["url"] == "https://example.com/thing"

    def test_an_unchecked_entry_is_not_rewritten(self):
        records = [entry(name="A", url="https://github.com/old/repo")]
        assert audit.follow_moves(records, [self.moved("A", "new/repo")],
                                  checked=set()) == []

    def test_other_findings_are_ignored(self):
        """Only a rename says where the project went."""
        records = [entry(name="A", url="https://github.com/old/repo")]
        archived = {"name": "A", "url": "", "issues": [{"kind": "archived", "detail": ""}]}

        assert audit.follow_moves(records, [archived]) == []

    def test_a_finding_with_no_destination_is_ignored(self):
        """A `moved` written by an older version carried only prose."""
        records = [entry(name="A", url="https://github.com/old/repo")]
        stale = {"name": "A", "url": "", "issues": [{"kind": "moved", "detail": "now at x/y"}]}

        assert audit.follow_moves(records, [stale]) == []

    def test_the_command_writes_the_change(self, monkeypatch):
        records = [entry(name="A", url="https://github.com/old/repo")]
        path = _write(records)
        monkeypatch.setattr(config, "AGENTS_JSON", path)
        monkeypatch.setattr(audit, "fetch_repo",
                            lambda repo, **kw: payload(full_name="new/repo"))

        assert audit.main(["--follow-moves"]) == 0
        assert json.loads(path.read_text())[0]["url"] == "https://github.com/new/repo"

    def test_it_refuses_when_something_could_not_be_checked(self, monkeypatch):
        def fake(repo, **kwargs):
            if repo == "acme/down":
                raise audit.Unavailable("HTTP 500")
            return payload(full_name="new/repo")

        monkeypatch.setattr(audit, "fetch_repo", fake)
        path = _write([entry(name="Down", url="https://github.com/acme/down"),
                       entry(name="A", url="https://github.com/old/repo")])
        monkeypatch.setattr(config, "AGENTS_JSON", path)

        assert audit.main(["--follow-moves"]) == 1
        assert json.loads(path.read_text())[1]["url"] == "https://github.com/old/repo"


class TestJsonOutputStaysParsable:
    """With --json, stdout is the data. The write-back messages used to land
    after the JSON array and make the file unusable for anything reading it —
    which is exactly what the weekly digest does."""

    def setup_catalogue(self, monkeypatch, archived=True):
        monkeypatch.setattr(audit, "fetch_repo",
                            lambda repo, **kw: payload(full_name="acme/a", archived=archived))
        path = _write([entry(name="A", url="https://github.com/acme/a")])
        monkeypatch.setattr(config, "AGENTS_JSON", path)
        return path

    def test_apply_status_and_json_together(self, monkeypatch, capsys):
        self.setup_catalogue(monkeypatch)

        assert audit.main(["--apply-status", "--json"]) == 0
        findings = json.loads(capsys.readouterr().out)
        assert findings[0]["name"] == "A"

    def test_follow_moves_and_json_together(self, monkeypatch, capsys):
        monkeypatch.setattr(audit, "fetch_repo",
                            lambda repo, **kw: payload(full_name="new/a"))
        monkeypatch.setattr(config, "AGENTS_JSON",
                            _write([entry(name="A", url="https://github.com/acme/a")]))

        assert audit.main(["--follow-moves", "--json"]) == 0
        assert isinstance(json.loads(capsys.readouterr().out), list)

    def test_the_human_report_still_says_what_it_did(self, monkeypatch, capsys):
        """Only --json redirects it; a person running this wants to see it."""
        self.setup_catalogue(monkeypatch)

        audit.main(["--apply-status"])
        assert "Updated" in capsys.readouterr().out
