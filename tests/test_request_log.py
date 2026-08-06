import logging

import pytest
from flask import Flask

import config
import request_log


@pytest.fixture
def app():
    application = Flask(__name__)

    @application.route('/fast')
    def fast():
        return {"ok": True}

    @application.route('/slow')
    def slow():
        # Burn a little real time so the measured duration is non-zero.
        import time
        time.sleep(0.02)
        return {"ok": True}

    @application.route('/boom')
    def boom():
        return {"error": "nope"}, 500

    request_log.register(application)
    return application


def test_adds_a_response_time_header(app):
    response = app.test_client().get('/fast')
    header = response.headers['X-Response-Time']
    assert header.endswith('ms')
    assert float(header[:-2]) >= 0


def test_logs_method_path_and_status(app, caplog):
    with caplog.at_level(logging.INFO, logger='request_log'):
        app.test_client().get('/fast')
    assert 'GET /fast -> 200' in caplog.text


def test_logs_error_responses_too(app, caplog):
    with caplog.at_level(logging.INFO, logger='request_log'):
        app.test_client().get('/boom')
    assert 'GET /boom -> 500' in caplog.text


def test_includes_the_query_string(app, caplog):
    with caplog.at_level(logging.INFO, logger='request_log'):
        app.test_client().get('/fast?limit=5')
    assert 'GET /fast?limit=5 -> 200' in caplog.text


def test_omits_a_trailing_question_mark_when_there_is_no_query(app, caplog):
    with caplog.at_level(logging.INFO, logger='request_log'):
        app.test_client().get('/fast')
    assert '/fast?' not in caplog.text


def test_slow_requests_are_logged_as_warnings(app, caplog, monkeypatch):
    monkeypatch.setattr(config, 'SLOW_REQUEST_MS', 1)  # everything is "slow"
    with caplog.at_level(logging.INFO, logger='request_log'):
        app.test_client().get('/slow')
    assert any(r.levelno == logging.WARNING for r in caplog.records)
    assert '(slow)' in caplog.text


def test_fast_requests_are_logged_at_info(app, caplog, monkeypatch):
    monkeypatch.setattr(config, 'SLOW_REQUEST_MS', 60_000)
    with caplog.at_level(logging.INFO, logger='request_log'):
        app.test_client().get('/fast')
    assert all(r.levelno == logging.INFO for r in caplog.records)
    assert '(slow)' not in caplog.text


def test_static_assets_are_not_logged(app, caplog, tmp_path):
    """Static files never touch Ollama or the index; logging them is noise."""
    # static_url_path must be explicit: Flask otherwise derives it from the
    # folder's basename, which is a random temp name here.
    application = Flask(__name__, static_folder=str(tmp_path), static_url_path='/static')
    (tmp_path / 'thing.css').write_text('body{}')
    request_log.register(application)

    with caplog.at_level(logging.INFO, logger='request_log'):
        response = application.test_client().get('/static/thing.css')

    assert response.status_code == 200
    assert 'thing.css' not in caplog.text
    # The timing header is still attached.
    assert 'X-Response-Time' in response.headers
