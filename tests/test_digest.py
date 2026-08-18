"""The weekly digest.

Reads what the other jobs already wrote, so everything here is offline. The
judgement being tested is what belongs in a summary: four step summaries and
two issues a week is four places to look and two to ignore, and a digest that
lists 115 names is the thing it was meant to replace.
"""

import json
import sys
from datetime import datetime, timedelta, timezone

import pytest

import config

sys.path.insert(0, str(config.PACKAGE_DIR))

import digest  # noqa: E402


def days_ago(n):
    return (datetime.now(timezone.utc) - timedelta(days=n)).isoformat()


def entry(**overrides):
    base = {"commit": "abc", "at": days_ago(1), "subject": "s", "total": 242,
            "added": [], "removed": [], "edited": []}
    base.update(overrides)
    return base


class TestTheWindow:
    def test_it_keeps_recent_entries(self):
        assert len(digest.recent([entry(at=days_ago(2))], days=7)) == 1

    def test_it_drops_older_ones(self):
        assert digest.recent([entry(at=days_ago(30))], days=7) == []

    def test_an_unreadable_date_is_kept(self):
        """Losing a real change is worse than including an old one, and the
        date is only used to pick the window."""
        assert len(digest.recent([entry(at="not a date"), entry(at=None)], days=7)) == 2

    def test_non_dict_entries_are_ignored(self):
        kept = digest.recent(["junk", None, entry(subject="real")], days=7)
        assert [e["subject"] for e in kept] == ["real"]


class TestSummarisingChanges:
    def test_it_totals_across_entries(self):
        summary = digest.summarise_changes([
            entry(added=["A"]), entry(added=["B"]), entry(removed=["C"])])

        assert summary["added"] == ["A", "B"]
        assert summary["removed"] == ["C"]

    def test_an_agent_touched_repeatedly_counts_once(self):
        """The question is what changed about the catalogue, not how many
        commits it took."""
        summary = digest.summarise_changes([
            entry(added=["A"]), entry(edited=[{"name": "A"}]), entry(edited=[{"name": "A"}])])

        assert summary["added"] == ["A"]
        assert summary["edited"] == []

    def test_added_and_removed_in_the_same_window_nets_out(self):
        """Reporting both is two pieces of news about a thing that is not
        there."""
        summary = digest.summarise_changes([entry(added=["Fleeting"]),
                                            entry(removed=["Fleeting"])])

        assert summary["added"] == [] and summary["removed"] == []

    def test_it_survives_a_damaged_changelog(self):
        summary = digest.summarise_changes([
            entry(added="not a list"), entry(removed=[None]),
            entry(edited=[{"nope": 1}, 7])])

        assert summary == {"added": [], "removed": [], "edited": []}

    def test_a_bare_string_where_an_object_belongs_is_salvaged(self):
        """`edited: ["Cursor"]` most likely means Cursor was edited. Dropping
        it loses a real change to save a shape check — the same tolerance the
        Atom feed applies."""
        summary = digest.summarise_changes([entry(edited=["Cursor"])])
        assert summary["edited"] == ["Cursor"]


class TestWhatNeedsAPerson:
    def finding(self, name, *kinds):
        return {"name": name, "url": "", "issues": [{"kind": k, "detail": f"{k} detail"}
                                                    for k in kinds]}

    def test_it_reports_findings_a_maintainer_must_decide_about(self):
        grouped = digest.summarise_findings([self.finding("A", "missing")])
        assert grouped["missing"] == [("A", "missing detail")]

    @pytest.mark.parametrize("kind", ["archived", "dormant"])
    def test_it_leaves_out_what_the_audit_already_acted_on(self, kind):
        """Those become a status automatically; listing them is a to-do item
        nobody has to do."""
        assert digest.summarise_findings([self.finding("A", kind)]) == {}

    def test_one_entry_can_need_a_decision_and_not(self):
        grouped = digest.summarise_findings([self.finding("A", "archived", "stack")])
        assert set(grouped) == {"stack"}

    def test_junk_does_not_crash_it(self):
        assert digest.summarise_findings(["nonsense", None, {}]) == {}


class TestRendering:
    def test_it_says_when_nothing_changed(self):
        text = digest.render({"added": [], "removed": [], "edited": []}, {}, 7)
        assert "Nothing changed" in text

    def test_it_says_when_nothing_needs_a_decision(self):
        """Silence could equally mean the audit never ran."""
        assert "Nothing outstanding" in digest.render(
            {"added": [], "removed": [], "edited": []}, {}, 7)

    def test_it_abbreviates_a_long_list(self):
        """A busy week added 115 agents; listing them all is the wall this
        replaces."""
        names = [f"Agent{i}" for i in range(40)]
        text = digest.render({"added": names, "removed": [], "edited": []}, {}, 7)

        assert "and 28 more" in text
        assert "Agent39" not in text

    def test_a_short_list_is_spelled_out(self):
        text = digest.render({"added": ["A", "B"], "removed": [], "edited": []}, {}, 7)
        assert "A, B" in text and "more" not in text

    def test_it_reports_the_catalogue_size(self):
        assert "**242**" in digest.render(
            {"added": [], "removed": [], "edited": []}, {}, 7, total=242)


class TestTheCommand:
    def write(self, tmp_path, entries):
        (tmp_path / "changelog.json").write_text(json.dumps(entries))
        return tmp_path

    def test_it_refuses_without_a_changelog(self, tmp_path, monkeypatch):
        """No history is not an empty week."""
        monkeypatch.setattr(config, "DATA_DIR", tmp_path)
        assert digest.main([]) == 1

    def test_it_prints_a_digest(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(config, "DATA_DIR", self.write(tmp_path, [entry(added=["Kedro"])]))

        assert digest.main([]) == 0
        assert "Kedro" in capsys.readouterr().out

    def test_it_can_write_to_a_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "DATA_DIR", self.write(tmp_path, [entry(added=["Kedro"])]))
        out = tmp_path / "digest.md"

        assert digest.main(["--out", str(out)]) == 0
        assert "Kedro" in out.read_text()

    def test_a_missing_audit_file_is_a_warning_not_a_failure(self, tmp_path, monkeypatch):
        """A missing audit is a smaller problem than no digest at all."""
        monkeypatch.setattr(config, "DATA_DIR", self.write(tmp_path, [entry(added=["A"])]))

        assert digest.main(["--audit", str(tmp_path / "absent.json")]) == 0

    def test_a_zero_window_is_refused(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "DATA_DIR", self.write(tmp_path, [entry()]))
        assert digest.main(["--days", "0"]) == 1


def test_a_malformed_issue_does_not_fail_the_whole_job():
    """The refresh workflow runs under `set -eo pipefail`, so a crash here
    fails everything after it rather than degrading to a changes-only
    digest."""
    findings = [{"name": "A", "issues": ["a string", None, 7,
                                         {"kind": "missing", "detail": "gone"}]}]
    assert digest.summarise_findings(findings) == {"missing": [("A", "gone")]}
