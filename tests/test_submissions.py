"""The proposal queue.

admin.py is a maintainer's tool and stays disabled by default. This is the
public half: anyone can propose an agent, but nothing reaches the catalogue
until a maintainer approves it.
"""

import json

import pytest
from flask import Flask

import admin
import config
import submissions


@pytest.fixture
def paths(tmp_path, monkeypatch):
    catalogue = tmp_path / "agents.json"
    catalogue.write_text(json.dumps([{
        "name": "Existing", "description": "Already here.", "category": "Automation",
        "tech_stack": [], "github_stars": 0, "url": "", "use_case": "",
    }]))
    monkeypatch.setattr(config, "AGENTS_JSON", catalogue)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "SUBMISSIONS_PATH", tmp_path / "submissions.jsonl")
    monkeypatch.setattr(config, "AUDIT_LOG_PATH", tmp_path / "audit.jsonl")
    return {"catalogue": catalogue, "queue": tmp_path / "submissions.jsonl"}


def proposal(**overrides):
    record = {
        "name": "Proposed", "description": "A proposed agent.", "category": "Automation",
        "tech_stack": ["Python"], "github_stars": 5, "url": "https://example.com",
        "use_case": "testing",
    }
    record.update(overrides)
    return record


class TestSubmitting:
    def test_a_valid_proposal_is_queued(self, paths):
        entry = submissions.submit(proposal())
        assert entry["status"] == submissions.PENDING
        assert entry["agent"]["name"] == "Proposed"
        assert entry["id"]

    def test_it_does_not_reach_the_catalogue(self, paths):
        submissions.submit(proposal())
        names = [r["name"] for r in json.loads(paths["catalogue"].read_text())]
        assert names == ["Existing"]

    def test_it_is_validated_like_an_edit(self, paths):
        with pytest.raises(admin.AdminError, match="'name' is required"):
            submissions.submit(proposal(name="  "))

    def test_a_name_already_in_the_catalogue_is_refused(self, paths):
        with pytest.raises(admin.AdminError, match="already exists"):
            submissions.submit(proposal(name="existing"))

    def test_a_name_already_pending_is_refused(self, paths):
        """Two people proposing the same agent should not both sit there."""
        submissions.submit(proposal(name="Twin"))
        with pytest.raises(admin.AdminError, match="already exists"):
            submissions.submit(proposal(name="twin"))

    def test_the_queue_survives_a_corrupt_line(self, paths):
        submissions.submit(proposal())
        with open(paths["queue"], "a") as f:
            f.write("{ not json\n")
        assert len(submissions.read_all()) == 1


class TestDeciding:
    def test_rejecting_records_the_decision(self, paths):
        entry = submissions.submit(proposal())
        decided = submissions.decide(entry["id"], submissions.REJECTED, note="not a fit")
        assert decided["status"] == submissions.REJECTED
        assert decided["note"] == "not a fit"

    def test_a_decision_cannot_be_made_twice(self, paths):
        entry = submissions.submit(proposal())
        submissions.decide(entry["id"], submissions.REJECTED)
        with pytest.raises(admin.AdminError, match="already"):
            submissions.decide(entry["id"], submissions.APPROVED)

    def test_an_unknown_id_is_404(self, paths):
        with pytest.raises(admin.AdminError, match="No submission"):
            submissions.decide("nope", submissions.APPROVED)

    def test_an_invalid_status_is_refused(self, paths):
        entry = submissions.submit(proposal())
        with pytest.raises(admin.AdminError, match="status must be"):
            submissions.decide(entry["id"], "maybe")

    def test_pending_count_tracks_decisions(self, paths):
        first = submissions.submit(proposal(name="One"))
        submissions.submit(proposal(name="Two"))
        assert submissions.pending_count() == 2

        submissions.decide(first["id"], submissions.REJECTED)
        assert submissions.pending_count() == 1

    def test_a_reset_returns_it_to_pending(self, paths):
        entry = submissions.submit(proposal())
        submissions.decide(entry["id"], submissions.APPROVED)
        restored = submissions.decide_reset(entry["id"])
        assert restored["status"] == submissions.PENDING
        assert "decided_at" not in restored


@pytest.fixture
def client(paths, monkeypatch, store):
    import api

    monkeypatch.setattr(config, "ENABLE_ADMIN", True)
    monkeypatch.setattr(config, "ENABLE_SUBMISSIONS", True)
    import rate_limit
    rate_limit.reset_all()
    api.set_store(store)

    app = Flask(__name__)
    app.register_blueprint(api.api_bp)
    app.register_blueprint(admin.admin_bp)
    api.register_error_handlers(app)
    admin.register_error_handler(app)
    with app.test_client() as test_client:
        yield test_client
    api.set_store(None)


class TestEndpoints:
    def test_submitting_is_public_and_returns_202(self, client):
        response = client.post("/api/submissions", json=proposal())
        assert response.status_code == 202
        body = response.get_json()
        assert body["status"] == "pending"
        assert "review" in body["note"]

    def test_a_bad_proposal_is_rejected_up_front(self, client):
        assert client.post("/api/submissions", json=proposal(url="javascript:x")).status_code == 400

    def test_submissions_can_be_closed(self, client, monkeypatch):
        monkeypatch.setattr(config, "ENABLE_SUBMISSIONS", False)
        assert client.post("/api/submissions", json=proposal()).status_code == 403

    def test_reviewing_requires_admin(self, client, monkeypatch):
        monkeypatch.setattr(config, "ENABLE_ADMIN", False)
        assert client.get("/api/admin/submissions").status_code == 403

    def test_approving_adds_it_to_the_catalogue(self, client, paths):
        submitted = client.post("/api/submissions", json=proposal()).get_json()
        response = client.post(f"/api/admin/submissions/{submitted['id']}/approve")
        assert response.status_code == 201

        names = [r["name"] for r in json.loads(paths["catalogue"].read_text())]
        assert "Proposed" in names

    def test_approving_is_audited_as_a_create(self, client, paths):
        """undo() understands create/delete/update; a bespoke "approve"
        action would block undo for every earlier change too."""
        submitted = client.post("/api/submissions", json=proposal()).get_json()
        client.post(f"/api/admin/submissions/{submitted['id']}/approve")

        entries = admin.read_audit()
        assert entries[0]["action"] == "create"
        assert entries[0]["name"] == "Proposed"

    def test_rejecting_keeps_it_out_of_the_catalogue(self, client, paths):
        submitted = client.post("/api/submissions", json=proposal()).get_json()
        response = client.post(f"/api/admin/submissions/{submitted['id']}/reject",
                               json={"note": "duplicate"})
        assert response.status_code == 200

        names = [r["name"] for r in json.loads(paths["catalogue"].read_text())]
        assert "Proposed" not in names

    def test_listing_filters_by_status(self, client):
        first = client.post("/api/submissions", json=proposal(name="One")).get_json()
        client.post("/api/submissions", json=proposal(name="Two"))
        client.post(f"/api/admin/submissions/{first['id']}/reject")

        pending = client.get("/api/admin/submissions?status=pending").get_json()
        assert [s["agent"]["name"] for s in pending["submissions"]] == ["Two"]
        assert pending["pending"] == 1

    def test_an_unknown_status_filter_is_refused(self, client):
        assert client.get("/api/admin/submissions?status=maybe").status_code == 400

    def test_status_reports_the_backlog(self, client):
        client.post("/api/submissions", json=proposal())
        assert client.get("/api/admin/status").get_json()["pending_submissions"] == 1

    def test_approval_is_reversible_when_the_name_was_taken_meanwhile(self, client, paths):
        """The catalogue can move on between proposal and review."""
        submitted = client.post("/api/submissions", json=proposal(name="Race")).get_json()

        # Someone adds the same name directly.
        client.post("/api/admin/agents", json=proposal(name="Race"))

        response = client.post(f"/api/admin/submissions/{submitted['id']}/approve")
        assert response.status_code == 409

        # The proposal is still reviewable rather than silently consumed.
        pending = client.get("/api/admin/submissions?status=pending").get_json()
        assert [s["id"] for s in pending["submissions"]] == [submitted["id"]]

    def test_submissions_are_rate_limited(self, client, monkeypatch):
        import rate_limit

        monkeypatch.setattr(rate_limit.submission_limiter, "limit", 2)
        rate_limit.reset_all()

        assert client.post("/api/submissions", json=proposal(name="A")).status_code == 202
        assert client.post("/api/submissions", json=proposal(name="B")).status_code == 202
        response = client.post("/api/submissions", json=proposal(name="C"))
        assert response.status_code == 429
        assert response.headers["Retry-After"]


class TestApprovalIsRecoverable:
    """A decision that cannot be carried out must not strand the proposal."""

    def test_a_write_failure_returns_it_to_pending(self, client, paths, monkeypatch):
        submitted = client.post("/api/submissions", json=proposal()).get_json()

        # Fails once, then works — monkeypatch.undo() would also revert the
        # ENABLE_ADMIN patch and make the follow-up request 403.
        original = admin.save_catalogue
        calls = []

        def explode_once(records):
            calls.append(1)
            if len(calls) == 1:
                raise admin.AdminError("disk full", status=500)
            return original(records)

        monkeypatch.setattr(admin, "save_catalogue", explode_once)
        assert client.post(f"/api/admin/submissions/{submitted['id']}/approve").status_code == 500

        pending = client.get("/api/admin/submissions?status=pending").get_json()
        assert [s["id"] for s in pending["submissions"]] == [submitted["id"]]

    def test_a_corrupt_catalogue_returns_it_to_pending(self, client, paths):
        submitted = client.post("/api/submissions", json=proposal()).get_json()
        paths["catalogue"].write_text("{ not json")

        assert client.post(f"/api/admin/submissions/{submitted['id']}/approve").status_code == 500
        assert submissions.pending_count() == 1

    def test_an_approval_can_be_undone(self, client, paths):
        """Audited as a create so undo() understands it; a bespoke action
        would block undo for every earlier change too."""
        submitted = client.post("/api/submissions", json=proposal()).get_json()
        client.post(f"/api/admin/submissions/{submitted['id']}/approve")

        assert client.post("/api/admin/undo").status_code == 200
        names = [r["name"] for r in json.loads(paths["catalogue"].read_text())]
        assert "Proposed" not in names


def test_rewriting_the_queue_keeps_lines_it_could_not_parse(paths):
    """An interrupted write leaves a truncated line. Reading tolerates it;
    rewriting used to delete it."""
    first = submissions.submit(proposal(name="Keeper"))
    with open(paths["queue"], "a") as f:
        f.write('{"id": "trunc", "agen\n')

    submissions.decide(first["id"], submissions.REJECTED)

    text = paths["queue"].read_text()
    assert '{"id": "trunc", "agen' in text, "the truncated line was destroyed"
    assert len(submissions.read_all()) == 1
