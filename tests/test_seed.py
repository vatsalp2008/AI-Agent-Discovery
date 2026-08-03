import json

import config
import scraper


def test_bootstraps_from_the_built_in_samples(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "AGENTS_JSON", tmp_path / "missing.json")
    assert len(scraper.load_agents()) == len(scraper.SAMPLE_AGENTS)


def test_prefers_the_on_disk_catalogue(agents_json):
    agents = scraper.load_agents()
    assert [a.name for a in agents] == ["Cursor", "Aider", "GPT Researcher"]


def test_empty_catalogue_falls_back_to_samples(agents_json):
    agents_json.write_text("[]")
    assert len(scraper.load_agents()) == len(scraper.SAMPLE_AGENTS)


def test_seeding_does_not_clobber_hand_edited_agents(agents_json, monkeypatch):
    """The README tells users to edit agents.json and re-run seed.py."""
    records = json.loads(agents_json.read_text())
    records.append({
        "name": "My Custom Agent",
        "description": "Added by hand.",
        "category": "Custom",
        "tech_stack": ["Python"],
        "github_stars": 1,
        "url": "https://example.com",
        "use_case": "Testing",
    })
    agents_json.write_text(json.dumps(records))

    monkeypatch.setattr(scraper, "VectorStore", _RecordingStore)
    scraper.seed_data()

    saved = [r["name"] for r in json.loads(agents_json.read_text())]
    assert "My Custom Agent" in saved
    assert len(saved) == 4


def test_reseeding_rebuilds_rather_than_appending(agents_json, monkeypatch):
    calls = []
    monkeypatch.setattr(scraper, "VectorStore", lambda: _RecordingStore(calls))

    scraper.seed_data()
    scraper.seed_data()

    assert [c[0] for c in calls] == ["replace", "replace"]
    assert {c[1] for c in calls} == {3}


def test_append_mode_adds_to_the_existing_index(agents_json, monkeypatch):
    calls = []
    monkeypatch.setattr(scraper, "VectorStore", lambda: _RecordingStore(calls))
    scraper.seed_data(rebuild=False)
    assert calls[0][0] == "add"


class _RecordingStore:
    """Captures how the seeder writes to the index."""

    def __init__(self, calls=None):
        self.calls = calls if calls is not None else []

    def replace_agents(self, agents):
        self.calls.append(("replace", len(agents)))

    def add_agents(self, agents):
        self.calls.append(("add", len(agents)))
