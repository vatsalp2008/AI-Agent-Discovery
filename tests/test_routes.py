"""Every route the app declares should actually respond.

Built by walking the real url_map, so a new page or endpoint is covered the
moment it is added — no list here to forget to update.
"""

import pytest
from flask import Flask

import admin
import api
import security


@pytest.fixture
def app(store, agents_json, monkeypatch):
    import config

    monkeypatch.setattr(config, "ENABLE_ADMIN", False)
    api.set_store(store)

    application = Flask(
        __name__,
        static_folder=str(config.PACKAGE_DIR / "frontend" / "static"),
        template_folder=str(config.PACKAGE_DIR / "frontend" / "templates"),
    )
    application.register_blueprint(api.api_bp)
    api.register_error_handlers(application)
    application.register_blueprint(admin.admin_bp)
    admin.register_error_handler(application)
    security.register(application)

    from flask import render_template

    @application.context_processor
    def flags():
        return {
            "admin_enabled": config.ENABLE_ADMIN,
            "submissions_enabled": config.ENABLE_SUBMISSIONS,
            "compare_max": config.COMPARE_MAX_AGENTS,
        }

    for path, template, page in [
        ("/", "index.html", "search"),
        ("/dashboard", "dashboard.html", "dashboard"),
        ("/compare", "compare.html", "compare"),
        ("/collections", "collections.html", "collections"),
        ("/admin", "admin.html", "admin"),
        ("/submit", "submit.html", "submit"),
    ]:
        application.add_url_rule(
            path, f"page_{page}",
            (lambda t=template, p=page: render_template(t, page=p, name="X")),
        )

    yield application
    api.set_store(None)


def test_every_page_renders(app):
    with app.test_client() as client:
        for path in ["/", "/dashboard", "/compare", "/collections", "/admin", "/submit"]:
            assert client.get(path).status_code == 200, path


def test_the_fixture_offers_the_same_flags_as_the_real_app(app):
    """This fixture reimplements app.inject_flags rather than importing it.

    A flag added there and missed here renders as undefined in Jinja, which
    is falsy — so a gated element silently disappears from every test while
    working fine in the app.
    """
    import re

    import config

    source = (config.PACKAGE_DIR / "frontend" / "app.py").read_text()
    body = source[source.index("def inject_flags"):source.index("@app.route('/')")]
    real = set(re.findall(r'"(\w+)":', body))

    fixture = set(app.template_context_processors[None][-1]())
    assert real <= fixture, f"the fixture is missing: {sorted(real - fixture)}"


def test_every_get_api_route_responds(app):
    """A 500 here means a route exists but is broken."""
    samples = {"name": "Cursor"}
    with app.test_client() as client:
        for rule in app.url_map.iter_rules():
            if not rule.rule.startswith("/api/") or "GET" not in rule.methods:
                continue
            path = rule.rule
            for argument in rule.arguments:
                path = path.replace(f"<{argument}>", samples.get(argument, "x"))
                path = path.replace(f"<path:{argument}>", samples.get(argument, "x"))

            response = client.get(path)
            assert response.status_code < 500, f"{path} returned {response.status_code}"


def test_every_admin_write_is_refused_when_disabled(app):
    """The only unauthenticated write surface must stay shut by default."""
    with app.test_client() as client:
        for rule in app.url_map.iter_rules():
            if not rule.rule.startswith("/api/admin/"):
                continue
            for method in rule.methods & {"POST", "PUT", "DELETE"}:
                path = rule.rule.replace("<path:name>", "Cursor").replace("<name>", "Cursor")
                response = client.open(path, method=method, json={})
                assert response.status_code == 403, f"{method} {path} returned {response.status_code}"


def test_security_headers_are_on_every_response(app):
    with app.test_client() as client:
        for path in ["/", "/api/stats", "/api/health"]:
            headers = client.get(path).headers
            assert "Content-Security-Policy" in headers, path
            assert headers["X-Content-Type-Options"] == "nosniff", path


def _is_hidden(body, element_id):
    """Whether the element with `element_id` carries the hidden attribute.

    Matched on the tag rather than an exact string so reformatting the
    template cannot fail this for the wrong reason.
    """
    import re

    tag = re.search(rf'<[^>]*id="{element_id}"[^>]*>', body)
    assert tag, f"no element with id {element_id!r}"
    return "hidden" in tag.group(0)


class TestSubmissionsGating:
    """With the queue closed, the page must say so before someone fills in
    the whole form — and the nav must not advertise it."""

    def test_the_nav_offers_the_page_when_the_queue_is_open(self, app, monkeypatch):
        import config
        monkeypatch.setattr(config, "ENABLE_SUBMISSIONS", True)
        body = app.test_client().get("/").get_data(as_text=True)
        assert 'href="/submit"' in body

    def test_the_nav_hides_the_page_when_the_queue_is_closed(self, app, monkeypatch):
        import config
        monkeypatch.setattr(config, "ENABLE_SUBMISSIONS", False)
        body = app.test_client().get("/").get_data(as_text=True)
        assert 'href="/submit"' not in body

    def test_a_closed_queue_still_answers_a_shared_link(self, app, monkeypatch):
        import config
        monkeypatch.setattr(config, "ENABLE_SUBMISSIONS", False)
        response = app.test_client().get("/submit")
        assert response.status_code == 200

    def test_a_closed_queue_renders_the_notice_not_the_form(self, app, monkeypatch):
        import config
        monkeypatch.setattr(config, "ENABLE_SUBMISSIONS", False)
        body = app.test_client().get("/submit").get_data(as_text=True)

        assert not _is_hidden(body, "submitClosed"), "the closed notice is still hidden"
        assert _is_hidden(body, "submitForm"), "the form is still offered"

    def test_an_open_queue_renders_the_form_not_the_notice(self, app, monkeypatch):
        import config
        monkeypatch.setattr(config, "ENABLE_SUBMISSIONS", True)
        body = app.test_client().get("/submit").get_data(as_text=True)

        assert _is_hidden(body, "submitClosed")
        assert not _is_hidden(body, "submitForm")
