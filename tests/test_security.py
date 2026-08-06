"""Baseline security headers on every response."""

import pytest
from flask import Flask

import security


@pytest.fixture
def app():
    application = Flask(__name__)

    @application.route('/')
    def index():
        return "<h1>hi</h1>"

    @application.route('/api/thing')
    def thing():
        return {"ok": True}

    security.register(application)
    return application


@pytest.mark.parametrize("header", [
    "Content-Security-Policy",
    "X-Content-Type-Options",
    "Referrer-Policy",
    "X-Frame-Options",
    "Permissions-Policy",
])
def test_header_is_present_on_html(app, header):
    assert header in app.test_client().get('/').headers


@pytest.mark.parametrize("header", ["Content-Security-Policy", "X-Content-Type-Options"])
def test_header_is_present_on_json(app, header):
    assert header in app.test_client().get('/api/thing').headers


def test_csp_disallows_inline_script():
    """No template has an inline <script>, so this stays enforceable."""
    csp = security.build_csp()
    script = [d for d in csp.split("; ") if d.startswith("script-src")][0]
    assert "'unsafe-inline'" not in script
    assert "'unsafe-eval'" not in script


def test_csp_allows_the_cdns_the_pages_actually_use():
    csp = security.build_csp()
    assert "https://unpkg.com" in csp          # ionicons
    assert "https://fonts.googleapis.com" in csp
    assert "https://fonts.gstatic.com" in csp


def test_csp_blocks_framing_and_stray_form_posts():
    csp = security.build_csp()
    assert "frame-ancestors 'none'" in csp
    assert "form-action 'self'" in csp
    assert "base-uri 'self'" in csp


def test_nosniff_is_set(app):
    assert app.test_client().get('/').headers["X-Content-Type-Options"] == "nosniff"


def test_referrer_policy_does_not_leak_queries(app):
    assert app.test_client().get('/').headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


def test_existing_headers_are_not_overwritten(app):
    """A route setting its own policy should win."""
    @app.route('/custom')
    def custom():
        return "x", 200, {"X-Frame-Options": "SAMEORIGIN"}

    assert app.test_client().get('/custom').headers["X-Frame-Options"] == "SAMEORIGIN"
