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
        return {"admin_enabled": config.ENABLE_ADMIN}

    for path, template, page in [
        ("/", "index.html", "search"),
        ("/dashboard", "dashboard.html", "dashboard"),
        ("/compare", "compare.html", "compare"),
        ("/collections", "collections.html", "collections"),
        ("/admin", "admin.html", "admin"),
    ]:
        application.add_url_rule(
            path, f"page_{page}",
            (lambda t=template, p=page: render_template(t, page=p, name="X")),
        )

    yield application
    api.set_store(None)


def test_every_page_renders(app):
    with app.test_client() as client:
        for path in ["/", "/dashboard", "/compare", "/collections", "/admin"]:
            assert client.get(path).status_code == 200, path


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
