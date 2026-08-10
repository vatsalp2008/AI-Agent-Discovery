"""Setup diagnostics.

The value of these checks is that they name the fix, so the tests assert on
the guidance as much as the status.
"""

import importlib.util
import json

import pytest
from conftest import BACKEND

import config

DOCTOR_PATH = BACKEND.parent / "doctor.py"


@pytest.fixture(scope="module")
def doctor():
    spec = importlib.util.spec_from_file_location("_doctor", DOCTOR_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestModelMatching:
    def test_a_bare_name_matches_its_default_tag(self, doctor):
        """Ollama reports "nomic-embed-text:latest" for a bare pull."""
        assert doctor._model_present(["nomic-embed-text:latest"], "nomic-embed-text")

    def test_an_explicit_tag_matches(self, doctor):
        assert doctor._model_present(["llama3.2:3b"], "llama3.2")

    def test_a_different_model_does_not_match(self, doctor):
        assert not doctor._model_present(["llama3.2:latest"], "mistral")

    def test_an_empty_list_matches_nothing(self, doctor):
        assert not doctor._model_present([], "llama3.2")


class TestCatalogueCheck:
    def test_reports_the_agent_count(self, doctor, tmp_path, monkeypatch):
        path = tmp_path / "agents.json"
        path.write_text(json.dumps([{"name": "A"}, {"name": "B"}]))
        monkeypatch.setattr(config, "AGENTS_JSON", path)

        result = doctor.check_catalogue()
        assert result["status"] == doctor.OK
        assert "2 agents" in result["detail"]

    def test_malformed_json_names_the_fix(self, doctor, tmp_path, monkeypatch):
        path = tmp_path / "agents.json"
        path.write_text("{ not json")
        monkeypatch.setattr(config, "AGENTS_JSON", path)

        result = doctor.check_catalogue()
        assert result["status"] == doctor.FAIL
        assert "not valid JSON" in result["detail"]
        assert result["fix"]

    def test_a_missing_catalogue_is_only_a_warning(self, doctor, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "AGENTS_JSON", tmp_path / "absent.json")
        result = doctor.check_catalogue()
        assert result["status"] == doctor.WARN
        assert result["required"] is False


class TestIndexCheck:
    def test_a_missing_index_says_to_seed(self, doctor, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "FAISS_DIR", tmp_path / "none")
        result = doctor.check_index()
        assert result["status"] == doctor.FAIL
        assert "seed.py" in result["fix"]

    def test_a_mismatched_model_is_a_failure(self, doctor, tmp_path, monkeypatch):
        index = tmp_path / "index"
        index.mkdir()
        (index / "index.faiss").write_bytes(b"stub")
        (index / "index_meta.json").write_text(json.dumps(
            {"embedding_model": "old-model", "agent_count": 3}))
        monkeypatch.setattr(config, "FAISS_DIR", index)
        monkeypatch.setattr(config, "EMBEDDING_MODEL", "new-model")

        result = doctor.check_index()
        assert result["status"] == doctor.FAIL
        assert "old-model" in result["detail"]

    def test_a_matching_model_passes(self, doctor, tmp_path, monkeypatch):
        index = tmp_path / "index"
        index.mkdir()
        (index / "index.faiss").write_bytes(b"stub")
        (index / "index_meta.json").write_text(json.dumps(
            {"embedding_model": "m", "agent_count": 7, "built_at": "2026-01-01T00:00:00+00:00"}))
        monkeypatch.setattr(config, "FAISS_DIR", index)
        monkeypatch.setattr(config, "EMBEDDING_MODEL", "m")

        result = doctor.check_index()
        assert result["status"] == doctor.OK
        assert "7 agents" in result["detail"]


class TestAdminCheck:
    def test_disabled_is_fine(self, doctor, monkeypatch):
        monkeypatch.setattr(config, "ENABLE_ADMIN", False)
        assert doctor.check_admin()["status"] == doctor.OK

    def test_enabled_on_localhost_is_fine(self, doctor, monkeypatch):
        monkeypatch.setattr(config, "ENABLE_ADMIN", True)
        monkeypatch.setattr(config, "HOST", "127.0.0.1")
        assert doctor.check_admin()["status"] == doctor.OK

    def test_enabled_on_a_public_host_warns(self, doctor, monkeypatch):
        """Editing has no authentication."""
        monkeypatch.setattr(config, "ENABLE_ADMIN", True)
        monkeypatch.setattr(config, "HOST", "0.0.0.0")

        result = doctor.check_admin()
        assert result["status"] == doctor.WARN
        assert "reachable from the network" in result["detail"]


class TestReport:
    def test_a_failure_is_summarised(self, doctor):
        output = doctor.render([
            {"check": "ollama", "status": doctor.FAIL, "detail": "down", "fix": "start it", "required": True},
        ])
        assert "1 check(s) failed" in output
        assert "-> start it" in output

    def test_all_clear_says_so(self, doctor):
        output = doctor.render([
            {"check": "x", "status": doctor.OK, "detail": "fine", "fix": None, "required": True},
        ])
        assert "Everything looks good" in output

    def test_warnings_do_not_read_as_failures(self, doctor):
        output = doctor.render([
            {"check": "x", "status": doctor.WARN, "detail": "meh", "fix": "do y", "required": False},
        ])
        assert "Everything required is in place" in output
        assert "1 warning" in output

    def test_a_passing_check_does_not_print_a_fix(self, doctor):
        output = doctor.render([
            {"check": "x", "status": doctor.OK, "detail": "fine", "fix": "unused", "required": True},
        ])
        assert "unused" not in output
