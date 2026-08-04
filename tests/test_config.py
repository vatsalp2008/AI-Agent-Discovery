"""Runtime settings must be safe by default."""

import importlib

import pytest

import config


@pytest.fixture
def fresh_config(monkeypatch):
    """Reload config with a controlled environment (ignoring any local .env)."""
    def _reload():
        monkeypatch.setattr(config, "load_dotenv", lambda *a, **k: None)
        return importlib.reload(config)
    yield _reload
    importlib.reload(config)


def test_debug_is_off_by_default(fresh_config, monkeypatch):
    """The Werkzeug debugger allows remote code execution."""
    monkeypatch.delenv("FLASK_DEBUG", raising=False)
    assert fresh_config().DEBUG is False


def test_host_defaults_to_loopback(fresh_config, monkeypatch):
    monkeypatch.delenv("HOST", raising=False)
    assert fresh_config().HOST == "127.0.0.1"


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
def test_debug_can_be_enabled_explicitly(fresh_config, monkeypatch, value):
    monkeypatch.setenv("FLASK_DEBUG", value)
    assert fresh_config().DEBUG is True


@pytest.mark.parametrize("value", ["0", "false", "no", "off", "", "banana"])
def test_other_values_leave_debug_off(fresh_config, monkeypatch, value):
    monkeypatch.setenv("FLASK_DEBUG", value)
    assert fresh_config().DEBUG is False


def test_port_is_configurable(fresh_config, monkeypatch):
    monkeypatch.setenv("PORT", "8080")
    assert fresh_config().PORT == 8080


def test_invalid_port_falls_back_to_the_default(fresh_config, monkeypatch):
    monkeypatch.setenv("PORT", "not-a-port")
    assert fresh_config().PORT == 5000
