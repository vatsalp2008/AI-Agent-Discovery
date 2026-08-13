"""Smoke tests against the real application object.

Every other test here builds its own Flask app, which is fast and isolated
but means app.py itself — the blueprint wiring, the context processor, the
request-size limit, the route table — is only exercised by running the
server. A mistake there passes the whole suite and fails on start.

Deliberately kept to what works without a seeded index: CI's unit job does
not seed, so anything touching the vector store belongs in tests-live.
"""

import sys

import pytest

import config

PAGES = ["/", "/dashboard", "/compare", "/collections", "/admin", "/submit"]


@pytest.fixture(scope="module")
def real_app():
    """The actual app object, imported the way the server imports it."""
    frontend = str(config.PACKAGE_DIR / "frontend")
    if frontend not in sys.path:
        sys.path.insert(0, frontend)

    from app import app
    app.config.update(TESTING=True)
    return app


def test_the_app_imports_and_wires_up(real_app):
    """Catches an import-time failure — a bad blueprint registration or a
    setting referenced before it exists — that no other test would see."""
    assert real_app.name
    assert real_app.url_map.iter_rules()


@pytest.mark.parametrize("path", PAGES)
def test_every_page_renders(real_app, path):
    assert real_app.test_client().get(path).status_code == 200


def test_every_static_route_actually_responds(real_app):
    """Built from the real url_map, so a route added without a template — or
    pointing at a renamed one — fails here rather than in production."""
    client = real_app.test_client()
    paths = [str(rule) for rule in real_app.url_map.iter_rules()
             if "<" not in str(rule) and not str(rule).startswith("/api")]

    assert len(paths) >= len(PAGES), "the url_map lost routes"
    for path in paths:
        assert client.get(path).status_code in (200, 301), path


def test_the_context_processor_reaches_the_templates(real_app):
    """inject_flags gates nav links. An undefined name is falsy in Jinja, so
    a broken processor silently hides them rather than raising."""
    with real_app.test_request_context("/"):
        flags = {}
        for processor in real_app.template_context_processors[None]:
            flags.update(processor())

    assert flags["admin_enabled"] is config.ENABLE_ADMIN
    assert flags["submissions_enabled"] is config.ENABLE_SUBMISSIONS


def test_the_request_size_limit_is_applied(real_app):
    """Set on the app rather than a route, so only the real app has it."""
    assert real_app.config["MAX_CONTENT_LENGTH"] == config.MAX_REQUEST_BYTES


def test_an_oversized_post_is_refused_with_json(real_app):
    response = real_app.test_client().post(
        "/api/submissions",
        data=b"x" * (config.MAX_REQUEST_BYTES + 1),
        content_type="application/json")

    assert response.status_code == 413
    assert response.get_json()["max_bytes"] == config.MAX_REQUEST_BYTES


def test_the_favicon_redirects_rather_than_404s(real_app):
    """Browsers request /favicon.ico directly, ignoring the <link> tag."""
    response = real_app.test_client().get("/favicon.ico")
    assert response.status_code == 301
    assert response.headers["Location"].endswith("favicon.svg")


@pytest.mark.parametrize("path", PAGES)
def test_no_script_is_included_twice(real_app, path):
    """base.html loads the shared scripts for every page, so a page that also
    lists one gets two tags. Loading a file twice re-runs its top-level
    `const`, which is a redeclaration error — and the asset guards in
    test_catalogue.py collect script names into a set, so a duplicate is
    invisible there. Only the rendered page shows it.
    """
    import re

    body = real_app.test_client().get(path).get_data(as_text=True)
    scripts = re.findall(r'<script src="/static/js/([^"]+)"', body)

    duplicated = {s for s in scripts if scripts.count(s) > 1}
    assert not duplicated, f"{path} loads {sorted(duplicated)} more than once"
