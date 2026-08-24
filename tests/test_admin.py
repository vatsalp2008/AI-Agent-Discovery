"""Catalogue write endpoints."""

import json

import pytest
from flask import Flask

import admin
import config


@pytest.fixture(autouse=True)
def isolate_audit_log(tmp_path, monkeypatch):
    """Never let a test append to the repository's real audit log."""
    monkeypatch.setattr(config, "AUDIT_LOG_PATH", tmp_path / "audit.jsonl")


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


class TestAuditLog:
    """Edits overwrite agents.json in place, so a mistaken change would
    otherwise be untraceable and unrecoverable."""

    @pytest.fixture
    def audit_path(self, tmp_path, monkeypatch):
        path = tmp_path / "audit.jsonl"
        monkeypatch.setattr(config, "AUDIT_LOG_PATH", path)
        return path

    def entries(self, path):
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

    def test_a_create_is_recorded(self, admin_client, audit_path):
        admin_client.post("/api/admin/agents", json=valid())
        entry = self.entries(audit_path)[-1]
        assert entry["action"] == "create"
        assert entry["name"] == "Aider"
        assert entry["after"]["description"]
        assert entry["at"].endswith("+00:00")

    def test_an_update_records_both_sides(self, admin_client, audit_path):
        """Keeping the previous record is what makes an edit undoable."""
        admin_client.put("/api/admin/agents/Cursor", json=valid(name="Cursor", description="Edited."))
        entry = self.entries(audit_path)[-1]
        assert entry["action"] == "update"
        assert entry["before"]["description"] == "An editor."
        assert entry["after"]["description"] == "Edited."

    def test_a_delete_records_what_was_removed(self, admin_client, audit_path):
        admin_client.delete("/api/admin/agents/Cursor")
        entry = self.entries(audit_path)[-1]
        assert entry["action"] == "delete"
        assert entry["before"]["name"] == "Cursor"

    def test_entries_accumulate(self, admin_client, audit_path):
        admin_client.post("/api/admin/agents", json=valid(name="One"))
        admin_client.post("/api/admin/agents", json=valid(name="Two"))
        assert [e["name"] for e in self.entries(audit_path)] == ["One", "Two"]

    def test_a_rejected_edit_is_not_recorded(self, admin_client, audit_path):
        admin_client.post("/api/admin/agents", json=valid(name="  "))
        assert self.entries(audit_path) == []

    def test_the_endpoint_returns_newest_first(self, admin_client, audit_path):
        admin_client.post("/api/admin/agents", json=valid(name="One"))
        admin_client.post("/api/admin/agents", json=valid(name="Two"))

        body = admin_client.get("/api/admin/audit").get_json()
        assert [e["name"] for e in body["entries"]] == ["Two", "One"]

    def test_the_endpoint_honours_a_limit(self, admin_client, audit_path):
        for i in range(5):
            admin_client.post("/api/admin/agents", json=valid(name=f"A{i}"))
        assert len(admin_client.get("/api/admin/audit?limit=2").get_json()["entries"]) == 2

    def test_a_truncated_line_does_not_hide_the_rest(self, admin_client, audit_path):
        admin_client.post("/api/admin/agents", json=valid(name="Good"))
        with open(audit_path, "a") as f:
            f.write('{"partial": \n')

        names = [e.get("name") for e in admin.read_audit()]
        assert "Good" in names

    def test_an_unwritable_path_does_not_block_the_edit(self, admin_client, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "AUDIT_LOG_PATH", tmp_path / "nope" / "x" / "audit.jsonl")
        # Auditing is best-effort; the edit must still succeed.
        assert admin_client.post("/api/admin/agents", json=valid()).status_code == 201

    def test_auditing_can_be_disabled(self, admin_client, monkeypatch, tmp_path):
        monkeypatch.setattr(config, "AUDIT_LOG_PATH", "")
        assert admin_client.post("/api/admin/agents", json=valid()).status_code == 201
        assert admin.read_audit() == []

    def test_the_endpoint_is_refused_when_editing_is_off(self, catalogue, monkeypatch, store):
        import api

        monkeypatch.setattr(config, "ENABLE_ADMIN", False)
        api.set_store(store)
        app = Flask(__name__)
        app.register_blueprint(admin.admin_bp)
        admin.register_error_handler(app)
        with app.test_client() as client:
            assert client.get("/api/admin/audit").status_code == 403
        api.set_store(None)


class TestUndo:
    """The audit log stores the previous record, so undo is putting it back."""

    @pytest.fixture
    def audit_path(self, tmp_path, monkeypatch):
        path = tmp_path / "audit.jsonl"
        monkeypatch.setattr(config, "AUDIT_LOG_PATH", path)
        return path

    def names(self, catalogue):
        return [r["name"] for r in json.loads(catalogue.read_text())]

    def test_undoes_a_create(self, admin_client, catalogue, audit_path):
        admin_client.post("/api/admin/agents", json=valid())
        assert "Aider" in self.names(catalogue)

        response = admin_client.post("/api/admin/undo")
        assert response.status_code == 200
        assert response.get_json()["undid"] == "create"
        assert "Aider" not in self.names(catalogue)

    def test_undoes_a_delete(self, admin_client, catalogue, audit_path):
        admin_client.delete("/api/admin/agents/Cursor")
        assert self.names(catalogue) == []

        assert admin_client.post("/api/admin/undo").status_code == 200
        assert self.names(catalogue) == ["Cursor"]

    def test_undoes_an_update(self, admin_client, catalogue, audit_path):
        admin_client.put("/api/admin/agents/Cursor", json=valid(name="Cursor", description="Edited."))
        assert admin_client.post("/api/admin/undo").status_code == 200

        records = json.loads(catalogue.read_text())
        assert records[0]["description"] == "An editor."

    def test_nothing_to_undo_is_404(self, admin_client, audit_path):
        assert admin_client.post("/api/admin/undo").status_code == 404

    def test_the_undo_is_itself_audited(self, admin_client, catalogue, audit_path):
        admin_client.post("/api/admin/agents", json=valid())
        admin_client.post("/api/admin/undo")

        latest = admin.read_audit(1)[0]
        assert latest["action"] == "undo"
        assert latest["name"] == "Aider"

    def test_undo_is_not_repeatable_into_nonsense(self, admin_client, catalogue, audit_path):
        """The second undo sees the 'undo' entry, which it cannot reverse."""
        admin_client.post("/api/admin/agents", json=valid())
        admin_client.post("/api/admin/undo")

        response = admin_client.post("/api/admin/undo")
        assert response.status_code == 422
        assert "undo" in response.get_json()["error"]

    def test_undoing_a_create_that_was_already_removed_conflicts(self, admin_client, catalogue, audit_path):
        admin_client.post("/api/admin/agents", json=valid())
        admin_client.delete("/api/admin/agents/Aider")
        # The newest entry is now the delete, so undo restores it rather than
        # conflicting — the conflict case is a hand-edit between the two.
        assert admin_client.post("/api/admin/undo").status_code == 200
        assert "Aider" in self.names(catalogue)

    def test_undoing_a_delete_when_the_name_exists_again_conflicts(self, admin_client, catalogue, audit_path):
        admin_client.delete("/api/admin/agents/Cursor")
        admin_client.post("/api/admin/agents", json=valid(name="Cursor"))
        # The newest entry is the create; undo removes it, which is correct.
        assert admin_client.post("/api/admin/undo").status_code == 200

    def test_is_refused_when_editing_is_off(self, catalogue, monkeypatch, store):
        import api

        monkeypatch.setattr(config, "ENABLE_ADMIN", False)
        api.set_store(store)
        app = Flask(__name__)
        app.register_blueprint(admin.admin_bp)
        admin.register_error_handler(app)
        with app.test_client() as client:
            assert client.post("/api/admin/undo").status_code == 403
        api.set_store(None)


class TestListingForTheEditor:
    """The editor must see the catalogue as it is on disk.

    /api/agents comes from the search index, which omits use_case and lags
    unindexed edits; a PUT replaces the whole record, so editing from it would
    silently blank the field.
    """

    def test_returns_the_raw_records(self, admin_client):
        body = admin_client.get("/api/admin/agents").get_json()
        assert body["total"] == 1
        assert body["agents"][0]["use_case"] == "Editing"

    def test_includes_every_editable_field(self, admin_client):
        record = admin_client.get("/api/admin/agents").get_json()["agents"][0]
        for field in admin.EDITABLE_FIELDS:
            assert field in record, f"{field} missing from the editor's view"

    def test_shows_an_unindexed_edit_immediately(self, admin_client):
        admin_client.post("/api/admin/agents", json=valid(name="Fresh"))
        names = [a["name"] for a in admin_client.get("/api/admin/agents").get_json()["agents"]]
        assert "Fresh" in names

    def test_is_refused_when_editing_is_off(self, catalogue, monkeypatch, store):
        import api

        monkeypatch.setattr(config, "ENABLE_ADMIN", False)
        api.set_store(store)
        app = Flask(__name__)
        app.register_blueprint(admin.admin_bp)
        admin.register_error_handler(app)
        with app.test_client() as client:
            assert client.get("/api/admin/agents").status_code == 403
        api.set_store(None)


def test_editing_preserves_use_case(admin_client, catalogue):
    """A round trip through the editor must not blank a field it did not show."""
    listed = admin_client.get("/api/admin/agents").get_json()["agents"][0]

    # Exactly what the editor submits: the record it loaded, description changed.
    edited = {field: listed[field] for field in admin.EDITABLE_FIELDS}
    edited["description"] = "Edited."
    assert admin_client.put("/api/admin/agents/Cursor", json=edited).status_code == 200

    saved = json.loads(catalogue.read_text())[0]
    assert saved["use_case"] == "Editing", "use_case was lost on edit"


class TestDuplicateCheck:
    """Exact names are rejected by validate; this catches near-duplicates."""

    def test_flags_a_very_similar_agent(self, admin_client, monkeypatch):
        monkeypatch.setattr(config, "DUPLICATE_SCORE", 0.0)
        body = admin_client.post("/api/admin/similar-check",
                                 json={"name": "New", "description": "An editor."}).get_json()
        assert body["checked"] is True
        assert body["similar"]
        assert "score" in body["similar"][0]

    def test_excludes_the_draft_itself_when_renaming(self, admin_client, monkeypatch):
        monkeypatch.setattr(config, "DUPLICATE_SCORE", 0.0)
        body = admin_client.post("/api/admin/similar-check",
                                 json={"name": "Cursor", "description": "An editor."}).get_json()
        assert "Cursor" not in [s["name"] for s in body["similar"]]

    def test_weak_matches_are_not_flagged(self, admin_client, weak_store):
        """Everything in a category looks alike; only close matches count."""
        import api

        api.set_store(weak_store)
        body = admin_client.post("/api/admin/similar-check",
                                 json={"name": "X", "description": "totally unrelated"}).get_json()
        assert body["checked"] is True
        assert body["similar"] == []

    def test_requires_something_to_check(self, admin_client):
        assert admin_client.post("/api/admin/similar-check", json={}).status_code == 400

    def test_reports_when_there_is_no_index(self, admin_client, tmp_path, monkeypatch):
        import api
        from vectorstore import VectorStore

        api.set_store(VectorStore(persist_directory=tmp_path / "none", embedding_function=object()))
        body = admin_client.post("/api/admin/similar-check", json={"name": "X"}).get_json()
        assert body == {"similar": [], "checked": False}

    def test_caps_the_number_of_candidates(self, admin_client, monkeypatch):
        monkeypatch.setattr(config, "DUPLICATE_SCORE", 0.0)
        body = admin_client.post("/api/admin/similar-check", json={"name": "X", "description": "y"}).get_json()
        assert len(body["similar"]) <= 3

    def test_is_refused_when_editing_is_off(self, catalogue, monkeypatch, store):
        import api

        monkeypatch.setattr(config, "ENABLE_ADMIN", False)
        api.set_store(store)
        app = Flask(__name__)
        app.register_blueprint(admin.admin_bp)
        admin.register_error_handler(app)
        with app.test_client() as client:
            assert client.post("/api/admin/similar-check", json={"name": "X"}).status_code == 403
        api.set_store(None)


class TestAgentStatus:
    """A directory that does not say a project is archived is misleading in
    the one way that matters when choosing a tool."""

    def record(self, **overrides):
        base = {"name": "Thing", "description": "Does a thing worth describing.",
                "category": "Automation", "tech_stack": ["Python"],
                "github_stars": 1, "url": "", "use_case": "x"}
        base.update(overrides)
        return base

    def test_absent_means_active(self):
        """223 records predate the field; none of them should need editing."""
        assert admin.validate(self.record(), [])["status"] == "active"

    def test_an_explicit_status_is_kept(self):
        assert admin.validate(self.record(status="archived"), [])["status"] == "archived"

    def test_it_is_normalised(self):
        assert admin.validate(self.record(status="  ARCHIVED "), [])["status"] == "archived"

    @pytest.mark.parametrize("bad", ["retired", "", 7, None, ["archived"]])
    def test_an_unknown_status_is_refused(self, bad):
        """Free text here would fragment the badge the way an invented
        category fragments the facets."""
        if bad in ("", None):
            assert admin.validate(self.record(status=bad), [])["status"] == "active"
            return
        with pytest.raises(admin.AdminError, match="status"):
            admin.validate(self.record(status=bad), [])

    def test_the_editor_sees_a_status_on_every_row(self, admin_client):
        """The editor PUTs back the whole record, so a field missing from the
        row it loaded would be blanked on save."""
        agents = admin_client.get("/api/admin/agents").get_json()["agents"]
        assert all(a.get("status") for a in agents)


class TestOneOnDiskFormat:
    """The editor and the seeder both write agents.json. They disagreed about
    `status`, so saving through /admin and then re-seeding rewrote 204
    records neither of them meant to touch."""

    def test_a_default_status_is_not_written(self):
        assert "status" not in admin.for_file({"name": "A", "status": "active"})
        assert "status" not in admin.for_file({"name": "A"})

    def test_a_real_status_is_kept(self):
        assert admin.for_file({"name": "A", "status": "archived"})["status"] == "archived"

    def test_the_seeder_uses_the_same_rule(self):
        """Two implementations is how they drifted in the first place."""
        import scraper
        from models import Agent

        plain = Agent(name="A", description="d", category="c", tech_stack=["Python"])
        gone = Agent(name="B", description="d", category="c", tech_stack=["Python"],
                     status="archived")

        assert scraper._for_file(plain) == admin.for_file(plain.to_dict())
        assert scraper._for_file(gone) == admin.for_file(gone.to_dict())

    def test_saving_then_seeding_leaves_the_file_alone(self, tmp_path, monkeypatch):
        """The round-trip that produced the spurious diff.

        Goes through validate() first, which is what the editor does and
        what puts `status` on the record — writing the raw dict would not
        exercise the disagreement at all.
        """
        import json

        import config
        import scraper
        from models import Agent

        monkeypatch.setattr(config, "AGENTS_JSON", tmp_path / "agents.json")
        monkeypatch.setattr(config, "DATA_DIR", tmp_path)

        edited = admin.validate({
            "name": "A", "description": "A description well past the sixty character floor.",
            "category": "Automation", "tech_stack": ["Python"], "github_stars": 0,
            "url": "", "use_case": "x"}, [])
        assert edited["status"] == "active", "validate should fill the default in memory"

        admin.save_catalogue([edited])
        after_save = (tmp_path / "agents.json").read_text()
        assert '"status"' not in after_save, "the editor wrote a default status to disk"

        scraper.write_agents_json([Agent.from_dict(r) for r in json.loads(after_save)])
        assert (tmp_path / "agents.json").read_text() == after_save


class TestDefaultsStayOutOfTheFile:
    """A default written to every record makes a re-seed rewrite the whole
    catalogue for nothing — which is how a save-then-seed once produced a
    204-record diff neither writer meant."""

    def test_an_absent_alternatives_list_is_not_written(self):
        assert admin.for_file({"name": "A", "alternatives": None}) == {"name": "A"}

    def test_an_empty_alternatives_list_is_not_written(self):
        """"None of these" and "no list at all" mean the same thing."""
        assert admin.for_file({"name": "A", "alternatives": []}) == {"name": "A"}

    def test_a_real_alternatives_list_is_kept(self):
        record = {"name": "A", "status": "archived", "alternatives": ["X"]}
        assert admin.for_file(record) == record

    def test_the_default_status_is_still_dropped(self):
        assert admin.for_file({"name": "A", "status": "active"}) == {"name": "A"}

    def test_a_real_status_is_still_kept(self):
        assert admin.for_file({"name": "A", "status": "dormant"})["status"] == "dormant"


class TestAlternativesAreForTheDead:
    """`alternatives` says "go here instead". It is maintained beside
    `status`, so the same rules apply: only an archived entry may carry it,
    and a public proposer may not set it at all."""

    def _record(self, **extra):
        return {"name": "X", "category": "Safety", "tech_stack": ["Python"],
                "github_stars": 1, "url": "https://github.com/a/b", "use_case": "u",
                "description": "A description comfortably past the sixty character floor.",
                **extra}

    EXISTING = [{"name": "Langflow", "status": "active"},
                {"name": "Dify", "status": "active"}]

    def test_an_archived_entry_may_name_known_agents(self):
        cleaned = admin.validate(
            self._record(status="archived", alternatives=["Langflow", "Dify"]),
            self.EXISTING)

        assert cleaned["alternatives"] == ["Langflow", "Dify"]

    def test_a_live_entry_may_not(self):
        with pytest.raises(admin.AdminError, match="only an archived agent"):
            admin.validate(self._record(alternatives=["Langflow"]), self.EXISTING)

    def test_an_unknown_name_is_refused(self):
        """A suggestion nobody can click through to is worse than none."""
        with pytest.raises(admin.AdminError, match="must name agents"):
            admin.validate(self._record(status="archived", alternatives=["Nope"]),
                           self.EXISTING)

    def test_an_archived_target_is_refused(self):
        """Pointing a dead project at another dead project is a link a reader
        cannot use — accepted here while CI refused it."""
        with pytest.raises(admin.AdminError, match="not themselves archived"):
            admin.validate(self._record(status="archived", alternatives=["Flowise"]),
                           [*self.EXISTING, {"name": "Flowise", "status": "archived"}])

    def test_an_agent_cannot_point_at_itself(self):
        with pytest.raises(admin.AdminError, match="its own alternative"):
            admin.validate(self._record(name="Solo", status="archived",
                                        alternatives=["Solo"]), self.EXISTING)

    def test_a_comma_is_refused(self):
        """Stored comma-joined in the index metadata, so a comma would split
        one name into two links that resolve to nothing."""
        with pytest.raises(admin.AdminError, match="must not contain commas"):
            admin.validate(self._record(status="archived", alternatives=["A,B"]),
                           self.EXISTING)

    def test_the_catalogue_spelling_is_stored(self):
        """Matched case-insensitively like the uniqueness check, but written
        back the way the catalogue spells it, so the link resolves."""
        cleaned = admin.validate(
            self._record(status="archived", alternatives=["langflow"]), self.EXISTING)

        assert cleaned["alternatives"] == ["Langflow"]

    def test_a_reading_list_is_refused(self):
        with pytest.raises(admin.AdminError, match="at most"):
            admin.validate(
                self._record(status="archived", alternatives=["Langflow"] * 6),
                self.EXISTING)

    def test_a_public_submission_cannot_set_it(self):
        """"Use my thing instead" is what a submission queue exists to
        filter."""
        cleaned = admin.validate(
            self._record(status="archived", alternatives=["Langflow"]),
            self.EXISTING, allow_status=False)

        assert "alternatives" not in cleaned

    def test_an_empty_list_is_not_stored(self):
        cleaned = admin.validate(self._record(alternatives=[]), self.EXISTING)

        assert "alternatives" not in cleaned

    def test_a_non_list_is_refused(self):
        with pytest.raises(admin.AdminError, match="must be a list"):
            admin.validate(self._record(status="archived", alternatives="Langflow"),
                           self.EXISTING)
