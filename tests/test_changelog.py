"""Building the catalogue's change history from git.

The diffing runs against plain dicts; only the few tests that need real
history touch a throwaway repository.
"""

import json
import subprocess
import sys

import pytest

import config

sys.path.insert(0, str(config.PACKAGE_DIR))

import changelog  # noqa: E402


def agent(name, **overrides):
    base = {"name": name, "description": f"{name} does a thing.", "category": "Framework",
            "tech_stack": ["Python"], "github_stars": 10, "url": f"https://e.com/{name}",
            "use_case": "testing"}
    base.update(overrides)
    return base


class TestComparingSnapshots:
    def test_an_added_agent(self):
        changes = changelog.compare([agent("A")], [agent("A"), agent("B")])
        assert changes["added"] == ["B"] and changes["removed"] == []

    def test_a_removed_agent(self):
        changes = changelog.compare([agent("A"), agent("B")], [agent("A")])
        assert changes["removed"] == ["B"] and changes["added"] == []

    def test_an_edited_field_is_named(self):
        """A re-categorisation and a rewritten description are not the same
        news, so "changed" is not enough."""
        changes = changelog.compare([agent("A")], [agent("A", category="Robotics")])

        assert changes["edited"] == [
            {"name": "A", "fields": [{"field": "category", "from": "Framework",
                                      "to": "Robotics"}]}
        ]

    def test_several_fields_on_one_agent(self):
        changes = changelog.compare(
            [agent("A")], [agent("A", category="Robotics", url="https://new")])
        assert {f["field"] for f in changes["edited"][0]["fields"]} == {"category", "url"}

    def test_a_star_change_is_not_reported(self):
        """A bot refreshes these weekly; including them would bury every
        addition under a wall of numbers."""
        assert changelog.compare([agent("A")], [agent("A", github_stars=99)])["edited"] == []

    def test_nothing_changed(self):
        changes = changelog.compare([agent("A")], [agent("A")])
        assert not any(changes.values())

    def test_an_empty_before_makes_everything_new(self):
        assert changelog.compare([], [agent("A")])["added"] == ["A"]

    def test_records_with_no_name_are_ignored(self):
        """A hand-edited file can hold anything; it must not crash the build."""
        changes = changelog.compare([{"description": "x"}, None], [agent("A")])
        assert changes["added"] == ["A"]

    def test_results_are_ordered(self):
        """So the same history produces the same file every time."""
        changes = changelog.compare([], [agent("C"), agent("A"), agent("B")])
        assert changes["added"] == ["A", "B", "C"]


class TestAbsentMeansDefault:
    def test_adding_a_default_status_is_not_a_change(self):
        """The commit that introduced `status` read as 204 agents edited, and
        the one that stopped writing the default read as 204 more."""
        before = [agent("A")]
        after = [agent("A", status="active")]
        assert changelog.compare(before, after)["edited"] == []

    def test_removing_a_default_status_is_not_a_change(self):
        assert changelog.compare([agent("A", status="active")], [agent("A")])["edited"] == []

    def test_a_real_status_change_is_still_reported(self):
        changes = changelog.compare([agent("A")], [agent("A", status="archived")])
        assert changes["edited"][0]["fields"] == [
            {"field": "status", "from": "active", "to": "archived"}
        ]

    @pytest.mark.parametrize("field,default", [("use_case", ""), ("url", "")])
    def test_other_defaults_too(self, field, default):
        before = [agent("A", **{field: default})]
        after = [{k: v for k, v in agent("A").items() if k != field}]
        assert changelog.compare(before, after)["edited"] == []


@pytest.fixture
def repo(tmp_path):
    """A throwaway git repository holding a catalogue with three revisions."""
    def run(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True,
                       capture_output=True, text=True)

    run("init", "-q")
    run("config", "user.email", "t@example.com")
    run("config", "user.name", "Test")

    (tmp_path / "data").mkdir()
    path = tmp_path / "data" / "agents.json"

    for message, records in [
        ("Start the catalogue", [agent("A")]),
        ("Add B", [agent("A"), agent("B")]),
        ("Recategorise A", [agent("A", category="Robotics"), agent("B")]),
    ]:
        path.write_text(json.dumps(records, indent=2))
        run("add", "data/agents.json")
        run("commit", "-q", "-m", message)

    return tmp_path


class TestBuildingFromHistory:
    def test_newest_first(self, repo):
        entries = changelog.build(repo_root=repo)
        assert [e["subject"] for e in entries] == [
            "Recategorise A", "Add B", "Start the catalogue"]

    def test_the_first_revision_is_a_starting_point(self, repo):
        """Reporting it as N agents "added" would date the whole catalogue to
        whenever the file was created."""
        first = changelog.build(repo_root=repo)[-1]
        assert first["added"] == [] and first["total"] == 1

    def test_each_entry_carries_its_changes(self, repo):
        entries = changelog.build(repo_root=repo)
        assert entries[1]["added"] == ["B"]
        assert entries[0]["edited"][0]["name"] == "A"

    def test_each_entry_records_the_size_at_that_point(self, repo):
        assert [e["total"] for e in changelog.build(repo_root=repo)] == [2, 2, 1]

    def test_outside_a_repository_it_builds_nothing(self, tmp_path):
        """Not an empty history — there is simply nothing to read, and
        writing [] would replace a good file with an empty one."""
        assert changelog.build(repo_root=tmp_path) == []

    def test_a_commit_touching_the_file_without_changing_it_is_skipped(self, repo):
        """Reformatting is not news."""
        path = repo / "data" / "agents.json"
        records = json.loads(path.read_text())
        path.write_text(json.dumps(records, indent=4))   # same data, new layout
        subprocess.run(["git", "commit", "-qam", "Reformat"], cwd=repo, check=True,
                       capture_output=True)

        assert "Reformat" not in [e["subject"] for e in changelog.build(repo_root=repo)]


class TestTheCommand:
    def test_it_refuses_to_write_an_empty_history(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "REPO_ROOT", tmp_path)
        monkeypatch.setattr(config, "DATA_DIR", tmp_path)

        assert changelog.main([]) == 1
        assert not (tmp_path / "changelog.json").exists()

    def test_it_writes_the_history(self, repo, tmp_path, monkeypatch):
        out = tmp_path / "out"
        out.mkdir()
        monkeypatch.setattr(config, "REPO_ROOT", repo)
        monkeypatch.setattr(config, "DATA_DIR", out)

        assert changelog.main([]) == 0
        entries = json.loads((out / "changelog.json").read_text())
        assert [e["subject"] for e in entries][0] == "Recategorise A"

    def test_a_dry_run_writes_nothing(self, repo, tmp_path, monkeypatch, capsys):
        out = tmp_path / "out"
        out.mkdir()
        monkeypatch.setattr(config, "REPO_ROOT", repo)
        monkeypatch.setattr(config, "DATA_DIR", out)

        assert changelog.main(["--dry-run"]) == 0
        assert not (out / "changelog.json").exists()
        assert "Recategorise A" in capsys.readouterr().out


def test_the_baseline_is_the_first_readable_revision(repo, monkeypatch):
    """If an earlier revision cannot be parsed, the first one that *can* is
    the starting point. Keying on the loop index dropped it instead, losing
    the catalogue's origin from the history entirely."""
    real = changelog.catalogue_at
    first = changelog.revisions("data/agents.json", repo)[0]["commit"]

    def unreadable(commit, path, root):
        return None if commit == first else real(commit, path, root)

    monkeypatch.setattr(changelog, "catalogue_at", unreadable)
    entries = changelog.build(repo_root=repo)

    assert [e["subject"] for e in entries][-1] == "Add B", "the baseline was dropped"
    assert entries[-1]["added"] == [], "the baseline reported its contents as new"


class TestNamesThatNoLongerExist:
    """A link to /agent/<name> 404s for anything the catalogue has dropped —
    including an agent this entry *added*, if a later commit removed it.
    Windsurf did exactly that after being renamed to Devin Desktop."""

    def test_an_agent_added_then_later_removed_is_marked(self, repo):
        path = repo / "data" / "agents.json"
        path.write_text(json.dumps([agent("A")]))          # B removed later
        subprocess.run(["git", "commit", "-qam", "Drop B"], cwd=repo, check=True,
                       capture_output=True)

        entries = changelog.build(repo_root=repo)
        added_b = next(e for e in entries if "B" in e["added"])

        assert "B" in added_b["gone"], "the entry that added B still links to it"

    def test_an_agent_that_survived_is_not_marked(self, repo):
        entries = changelog.build(repo_root=repo)
        added_b = next(e for e in entries if "B" in e["added"])

        assert added_b["gone"] == []

    def test_every_entry_carries_the_field(self, repo):
        """So the page can rely on it rather than falling back."""
        assert all("gone" in e for e in changelog.build(repo_root=repo))

    def test_a_removed_agent_is_marked_in_its_own_entry(self, repo):
        path = repo / "data" / "agents.json"
        path.write_text(json.dumps([agent("A")]))
        subprocess.run(["git", "commit", "-qam", "Drop B"], cwd=repo, check=True,
                       capture_output=True)

        removal = next(e for e in changelog.build(repo_root=repo) if e["removed"])
        assert removal["gone"] == ["B"]


class TestSinceIsReadOnly:
    """--since builds a window, not a history. Writing it replaced the whole
    file with a slice, and the window's oldest commit became a zero-change
    baseline — so its additions were lost as well as everything before it."""

    def test_it_refuses_to_write(self, repo, tmp_path, monkeypatch):
        out = tmp_path / "out"
        out.mkdir()
        monkeypatch.setattr(config, "REPO_ROOT", repo)
        monkeypatch.setattr(config, "DATA_DIR", out)

        assert changelog.main(["--since", "2000-01-01"]) == 1
        assert not (out / "changelog.json").exists()

    def test_it_does_not_overwrite_an_existing_history(self, repo, tmp_path, monkeypatch):
        out = tmp_path / "out"
        out.mkdir()
        monkeypatch.setattr(config, "REPO_ROOT", repo)
        monkeypatch.setattr(config, "DATA_DIR", out)

        changelog.main([])
        full = (out / "changelog.json").read_text()

        changelog.main(["--since", "2000-01-01"])
        assert (out / "changelog.json").read_text() == full

    def test_a_dry_run_is_still_allowed(self, repo, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(config, "REPO_ROOT", repo)
        monkeypatch.setattr(config, "DATA_DIR", tmp_path)

        assert changelog.main(["--since", "2000-01-01", "--dry-run"]) == 0
        assert capsys.readouterr().out.strip()


def test_the_history_cannot_describe_its_own_commit(repo):
    """changelog.py reads git history, so a rebuild run before committing
    produces a history one commit behind — describing the state before the
    change it was run for. The weekly workflow avoids this by rebuilding in
    its own commit; this pins the reason.
    """
    path = repo / "data" / "agents.json"
    path.write_text(json.dumps([agent("A"), agent("B"), agent("C")]))

    # Built while the change is only in the working tree.
    before_commit = changelog.build(repo_root=repo)
    assert before_commit[0]["total"] == 2, "an uncommitted change was somehow visible"

    subprocess.run(["git", "commit", "-qam", "Add C"], cwd=repo, check=True,
                   capture_output=True)

    after_commit = changelog.build(repo_root=repo)
    assert after_commit[0]["total"] == 3
    assert after_commit[0]["added"] == ["C"]
