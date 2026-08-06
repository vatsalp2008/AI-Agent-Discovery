"""Text and JSON log formats."""

import json
import logging

import pytest

import config
import logging_setup


@pytest.fixture(autouse=True)
def clean_logging():
    logging_setup.reset()
    yield
    logging_setup.reset()


def _emit(capsys, level="INFO", **kwargs):
    logging_setup.configure(level)
    logging.getLogger("test.logger").info("hello %s", "world", **kwargs)
    return capsys.readouterr().err.strip()


def test_text_format_is_human_readable(capsys, monkeypatch):
    monkeypatch.setattr(config, "LOG_FORMAT", "text")
    line = _emit(capsys)
    assert "hello world" in line
    assert "test.logger" in line
    assert not line.startswith("{")


def test_json_format_emits_one_object_per_line(capsys, monkeypatch):
    monkeypatch.setattr(config, "LOG_FORMAT", "json")
    record = json.loads(_emit(capsys))
    assert record["message"] == "hello world"
    assert record["level"] == "INFO"
    assert record["logger"] == "test.logger"
    assert record["timestamp"].endswith("+00:00")


def test_json_format_promotes_extra_fields_to_keys(capsys, monkeypatch):
    """request_log attaches fields via extra=; they must be real JSON keys."""
    monkeypatch.setattr(config, "LOG_FORMAT", "json")
    logging_setup.configure("INFO")
    logging.getLogger("api").info(
        "request", extra={"path": "/api/search", "status": 200, "duration_ms": 12.5}
    )
    record = json.loads(capsys.readouterr().err.strip())
    assert record["path"] == "/api/search"
    assert record["status"] == 200
    assert record["duration_ms"] == 12.5


def test_json_format_includes_tracebacks(capsys, monkeypatch):
    monkeypatch.setattr(config, "LOG_FORMAT", "json")
    logging_setup.configure("INFO")
    try:
        raise ValueError("boom")
    except ValueError:
        logging.getLogger("api").exception("failed")

    record = json.loads(capsys.readouterr().err.strip())
    assert "ValueError: boom" in record["exception"]


def test_json_format_survives_an_unserializable_extra(capsys, monkeypatch):
    monkeypatch.setattr(config, "LOG_FORMAT", "json")
    logging_setup.configure("INFO")
    logging.getLogger("api").info("odd", extra={"obj": object()})

    record = json.loads(capsys.readouterr().err.strip())
    assert "object object" in record["obj"]


def test_configure_is_idempotent(capsys, monkeypatch):
    """A second call must not double every line."""
    monkeypatch.setattr(config, "LOG_FORMAT", "text")
    logging_setup.configure("INFO")
    logging_setup.configure("INFO")
    logging.getLogger("x").info("once")
    assert capsys.readouterr().err.strip().count("once") == 1


def test_unknown_format_falls_back_to_text(capsys, monkeypatch):
    monkeypatch.setattr(config, "LOG_FORMAT", "yaml-please")
    assert not _emit(capsys).startswith("{")
