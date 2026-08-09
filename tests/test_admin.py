"""Catalogue write endpoints."""

import json

import pytest
from flask import Flask

import admin
import config


@pytest.fixture
def catalogue(tmp_path, monkeypatch):
    path = tmp_path / "agents.json"
    path.write_text(json.dumps([{
        "name": "Cursor", "description": "An editor.", "category": "Code Generation",
        "tech_stack": ["Electron"], "github_stars": 100, "url": "https://cursor.sh",
        "use_case": "Editing",
    }], indent=2) + "\n")
    monkeypatch.setattr(config, "AGENTS_JSON", path)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    return path


@pytest.fixture
def admin_client(catalogue, monkeypatch, store):
    import api

    monkeypatch.setattr(config, "ENABLE_ADMIN", True)
    api.set_store(store)

    app = Flask(__name__)
    app.register_blueprint(admin.admin_bp)
    admin.register_error_handler(app)
    with app.test_client() as client:
        yield client
    api.set_store(None)


def valid(**overrides):
    record = {
        "name": "Aider", "description": "Terminal pair programming.",
        "category": "Code Generation", "tech_stack": ["Python", "Git"],
        "github_stars": 500, "url": "https://github.com/paul-gauthier/aider",
        "use_case": "Pair programming",
    }
    record.update(overrides)
    return record


class TestDisabledByDefault:
    def test_writes_are_refused_when_disabled(self, catalogue, monkeypatch, store):
        import api

        monkeypatch.setattr(config, "ENABLE_ADMIN", False)
        api.set_store(store)
        app = Flask(__name__)
        app.register_blueprint(admin.admin_bp)
        admin.register_error_handler(app)

        with app.test_client() as client:
            for call in [
                lambda: client.post("/api/admin/agents", json=valid()),
                lambda: client.put("/api/admin/agents/Cursor", json=valid()),
                lambda: client.delete("/api/admin/agents/Cursor"),
            ]:
                response = call()
                assert response.status_code == 403
                assert "ENABLE_ADMIN" in response.get_json()["error"]
        api.set_store(None)

    def test_the_default_is_off(self):
        """This is the only unauthenticated write surface in the app."""
        assert config.ENABLE_ADMIN is False


class TestCreate:
    def test_adds_an_agent(self, admin_client, catalogue):
        response = admin_client.post("/api/admin/agents", json=valid())
        assert response.status_code == 201
        assert response.get_json()["total"] == 2
        assert "Aider" in [r["name"] for r in json.loads(catalogue.read_text())]

    def test_rejects_a_duplicate_name(self, admin_client):
        response = admin_client.post("/api/admin/agents", json=valid(name="cursor"))
        assert response.status_code == 409

    @pytest.mark.parametrize("field", ["name", "description", "category"])
    def test_requires_the_core_fields(self, admin_client, field):
        response = admin_client.post("/api/admin/agents", json=valid(**{field: "  "}))
        assert response.status_code == 400
        assert field in response.get_json()["error"]

    def test_rejects_unknown_fields(self, admin_client):
        response = admin_client.post("/api/admin/agents", json={**valid(), "bogus": 1})
        assert response.status_code == 400
        assert "bogus" in response.get_json()["error"]

    def test_rejects_a_comma_in_a_tech_entry(self, admin_client):
        """stack is stored comma-joined, so a comma would split the entry."""
        response = admin_client.post("/api/admin/agents", json=valid(tech_stack=["Python, Git"]))
        assert response.status_code == 400

    @pytest.mark.parametrize("stars", [-1, "many", True, 1.5])
    def test_rejects_bad_star_counts(self, admin_client, stars):
        assert admin_client.post("/api/admin/agents", json=valid(github_stars=stars)).status_code == 400

    def test_rejects_a_non_http_url(self, admin_client):
        assert admin_client.post("/api/admin/agents", json=valid(url="javascript:alert(1)")).status_code == 400

    def test_allows_an_empty_url(self, admin_client):
        assert admin_client.post("/api/admin/agents", json=valid(url="")).status_code == 201

    def test_rejects_a_non_object_body(self, admin_client):
        assert admin_client.post("/api/admin/agents", json=["nope"]).status_code == 400


class TestUpdate:
    def test_edits_an_agent(self, admin_client, catalogue):
        response = admin_client.put("/api/admin/agents/Cursor",
                                    json=valid(name="Cursor", description="Updated."))
        assert response.status_code == 200
        records = json.loads(catalogue.read_text())
        assert records[0]["description"] == "Updated."

    def test_can_rename(self, admin_client, catalogue):
        assert admin_client.put("/api/admin/agents/Cursor", json=valid(name="Renamed")).status_code == 200
        assert [r["name"] for r in json.loads(catalogue.read_text())] == ["Renamed"]

    def test_keeping_its_own_name_is_not_a_conflict(self, admin_client):
        assert admin_client.put("/api/admin/agents/Cursor", json=valid(name="Cursor")).status_code == 200

    def test_unknown_agent_is_404(self, admin_client):
        assert admin_client.put("/api/admin/agents/Ghost", json=valid()).status_code == 404

    def test_is_case_insensitive(self, admin_client):
        assert admin_client.put("/api/admin/agents/cursor", json=valid(name="Cursor")).status_code == 200


class TestDelete:
    def test_removes_an_agent(self, admin_client, catalogue):
        response = admin_client.delete("/api/admin/agents/Cursor")
        assert response.status_code == 200
        assert response.get_json()["total"] == 0
        assert json.loads(catalogue.read_text()) == []

    def test_unknown_agent_is_404(self, admin_client):
        assert admin_client.delete("/api/admin/agents/Ghost").status_code == 404


class TestStatus:
    def test_reports_whether_editing_is_available(self, admin_client):
        body = admin_client.get("/api/admin/status").get_json()
        assert body["enabled"] is True
        assert body["total"] == 1


def test_writes_are_atomic(admin_client, catalogue, tmp_path):
    """A crash mid-write must not truncate the catalogue."""
    admin_client.post("/api/admin/agents", json=valid())
    assert not (tmp_path / "agents.json.tmp").exists()
    json.loads(catalogue.read_text())  # still valid JSON


def test_catalogue_keeps_a_trailing_newline(admin_client, catalogue):
    admin_client.post("/api/admin/agents", json=valid())
    assert catalogue.read_text().endswith("]\n")


class TestReindex:
    def test_rebuilds_the_index(self, admin_client, store, catalogue, monkeypatch):
        import scraper

        monkeypatch.setattr(scraper, "load_agents",
                            lambda: [__import__("models").Agent.from_dict(r)
                                     for r in json.loads(catalogue.read_text())])
        response = admin_client.post("/api/admin/reindex")
        assert response.status_code == 200
        assert response.get_json()["indexed"] >= 1

    def test_is_refused_when_disabled(self, catalogue, monkeypatch, store):
        import api

        monkeypatch.setattr(config, "ENABLE_ADMIN", False)
        api.set_store(store)
        app = Flask(__name__)
        app.register_blueprint(admin.admin_bp)
        admin.register_error_handler(app)
        with app.test_client() as client:
            assert client.post("/api/admin/reindex").status_code == 403
        api.set_store(None)

    def test_a_broken_catalogue_is_reported_not_raised(self, admin_client, catalogue):
        catalogue.write_text("{ not json")
        response = admin_client.post("/api/admin/reindex")
        assert response.status_code == 400
        assert "not valid JSON" in response.get_json()["error"]


class TestMalformedExistingRecords:
    """The catalogue is hand-editable, so existing entries may be broken.
    Validating a *new* record must not 500 because an *old* one is bad."""

    def test_a_record_missing_a_name_does_not_break_validation(self, admin_client, catalogue):
        catalogue.write_text(json.dumps([{"description": "no name here"}]))
        response = admin_client.post("/api/admin/agents", json=valid())
        assert response.status_code == 201

    def test_a_non_dict_entry_does_not_break_validation(self, admin_client, catalogue):
        catalogue.write_text(json.dumps(["just a string"]))
        assert admin_client.post("/api/admin/agents", json=valid()).status_code == 201

    def test_a_non_string_name_does_not_break_validation(self, admin_client, catalogue):
        catalogue.write_text(json.dumps([{"name": 123}]))
        assert admin_client.post("/api/admin/agents", json=valid()).status_code == 201

    def test_duplicates_are_still_caught_among_valid_records(self, admin_client, catalogue):
        catalogue.write_text(json.dumps([{"name": "Aider"}, {"broken": True}]))
        assert admin_client.post("/api/admin/agents", json=valid(name="aider")).status_code == 409


def test_writes_work_when_the_catalogue_sits_outside_data_dir(tmp_path, monkeypatch, store):
    """AGENTS_JSON is configurable independently of DATA_DIR."""
    import api

    elsewhere = tmp_path / "elsewhere" / "agents.json"
    monkeypatch.setattr(config, "AGENTS_JSON", elsewhere)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "ENABLE_ADMIN", True)
    api.set_store(store)

    app = Flask(__name__)
    app.register_blueprint(admin.admin_bp)
    admin.register_error_handler(app)
    with app.test_client() as client:
        assert client.post("/api/admin/agents", json=valid()).status_code == 201
    assert elsewhere.exists()
    api.set_store(None)


def test_concurrent_creates_do_not_drop_each_other(catalogue, monkeypatch, store):
    """Each edit is a read-modify-write of the whole file, so without a lock
    the second write would silently discard the first — both returning 201."""
    import threading

    import api

    monkeypatch.setattr(config, "ENABLE_ADMIN", True)
    api.set_store(store)

    app = Flask(__name__)
    app.register_blueprint(admin.admin_bp)
    admin.register_error_handler(app)

    errors = []

    def add(i):
        # A test client is not shareable across threads; give each its own.
        with app.test_client() as client:
            response = client.post("/api/admin/agents", json=valid(name=f"Agent{i}"))
            if response.status_code != 201:
                errors.append((i, response.status_code, response.get_json()))

    threads = [threading.Thread(target=add, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    api.set_store(None)
    assert not errors, errors

    names = {r["name"] for r in json.loads(catalogue.read_text())}
    expected = {f"Agent{i}" for i in range(8)} | {"Cursor"}
    assert names == expected, f"lost writes: {sorted(expected - names)}"
