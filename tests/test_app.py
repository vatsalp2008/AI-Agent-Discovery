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


def _page_paths(app):
    """Every page route the app declares, taken from the url_map.

    A hardcoded list goes stale silently: /saved was added without being
    added here, so the duplicate-script guard never rendered the one page it
    was written for — and that page is the only one with its own
    `{% block scripts %}`.
    """
    paths = []
    for rule in app.url_map.iter_rules():
        path = str(rule)
        if path.startswith(("/api", "/static")) or "<" in path or path == "/favicon.ico":
            continue
        paths.append(path)
    return sorted(paths)


# Kept for the parametrised cases, which need the list at collection time.
PAGES = ["/", "/dashboard", "/compare", "/collections", "/saved", "/changes",
         "/tech", "/admin", "/submit"]


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


def test_an_oversized_post_is_refused_with_json(real_app, monkeypatch):
    # The route rejects a closed queue with 403 before the body is read, so
    # without pinning this the test asserts 413 against whatever the
    # environment happens to set.
    monkeypatch.setattr(config, "ENABLE_SUBMISSIONS", True)
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


def test_the_page_list_matches_the_app(real_app):
    """PAGES drives the parametrised guards below, so a page missing from it
    is a page nothing checks."""
    assert set(_page_paths(real_app)) == set(PAGES)


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


def test_the_readme_lists_every_page(real_app):
    """The Pages table is how someone finds a feature exists at all.

    A page added without a row is invisible; a row left behind after a route
    is removed sends people to a 404. Both are the kind of drift nobody
    notices, because the table looks authoritative either way.
    """
    import re

    readme = (config.REPO_ROOT / "README.md").read_text()
    # A row may show an example query string — `/compare?names=A,B` — which
    # still documents the route.
    documented = {path.split("?")[0]
                  for path in re.findall(r"^\| `(/[^`]*)`", readme, flags=re.M)}

    # Routes a reader would navigate to: no API, no static, no redirects.
    real = set()
    for rule in real_app.url_map.iter_rules():
        path = str(rule)
        if path.startswith("/api") or path.startswith("/static") or path == "/favicon.ico":
            continue
        # Parameterised routes are documented with their placeholder name.
        real.add(re.sub(r"<[^>]*?([\w]+)>", r"<\1>", path))

    missing = real - documented
    assert not missing, f"pages the README does not list: {sorted(missing)}"


# Page script -> (template, the fixture in tests-js/helpers.js standing in for it)
PAGE_SCRIPTS = {
    "main.js": ("index.html", "SEARCH_HTML"),
    "saved-page.js": ("saved.html", "SAVED_HTML"),
    "collections-page.js": ("collections.html", "COLLECTIONS_HTML"),
    "compare.js": ("compare.html", "COMPARE_HTML"),
    "tech.js": ("tech.html", "TECH_HTML"),
    "changes.js": ("changes.html", "CHANGES_HTML"),
    "tech-index.js": ("tech-index.html", "TECH_INDEX_HTML"),
    "dashboard.js": ("dashboard.html", "DASHBOARD_HTML"),
    "submit.js": ("submit.html", "SUBMIT_HTML"),
    "admin.js": ("admin.html", "ADMIN_HTML"),
}


@pytest.mark.parametrize("script,template,fixture", [
    (s, t, f) for s, (t, f) in PAGE_SCRIPTS.items()
])
def test_page_scripts_only_reach_for_elements_that_exist(script, template, fixture):
    """Every getElementById in a page script must resolve — in the real
    template *and* in the hand-written fixture the JS tests boot against.

    The fixture half is the one that keeps going wrong. It has drifted three
    times: SUBMIT_HTML lost its labels, so the accessibility check passed on
    a page with none; SEARCH_HTML went stale when a script was added; and a
    fixture that is missing an element simply makes the page script skip that
    feature, so the tests stay green while the page is broken.
    """
    import re

    js = config.PACKAGE_DIR / "frontend" / "static" / "js"
    templates = config.PACKAGE_DIR / "frontend" / "templates"
    helpers = (config.REPO_ROOT / "tests-js" / "helpers.js").read_text()

    used = set(re.findall(r"getElementById\('([^']+)'\)", (js / script).read_text()))
    assert used, f"{script} looks up no elements; has it been rewritten?"

    in_template = set(re.findall(r'id="([^"]+)"', (templates / template).read_text()))
    assert not (used - in_template), \
        f"{script} reaches for ids missing from {template}: {sorted(used - in_template)}"

    block = re.search(rf"export const {fixture} = `(.*?)`;", helpers, re.S)
    assert block, f"tests-js/helpers.js no longer exports {fixture}"

    in_fixture = set(re.findall(r'id="([^"]+)"', block.group(1)))
    assert not (used - in_fixture), \
        f"{fixture} is missing ids {script} uses: {sorted(used - in_fixture)}"


def test_the_compare_limit_reaches_the_page(real_app):
    """The client stops its picker and builds /compare links from this. Both
    sides hardcoding 8 meant setting COMPARE_MAX_AGENTS=4 produced links the
    API refuses with a 400 — the exact failure the limit exists to prevent.
    """
    import re

    body = real_app.test_client().get("/compare").get_data(as_text=True)
    published = re.search(r'data-compare-max="(\d+)"', body)

    assert published, "the page no longer publishes the compare limit"
    assert int(published.group(1)) == config.COMPARE_MAX_AGENTS


def test_every_page_publishes_it(real_app):
    """It lives on <body> in base.html, so any page that builds a compare
    link — collections, for one — can read it."""
    import re

    client = real_app.test_client()
    for path in PAGES:
        body = client.get(path).get_data(as_text=True)
        assert re.search(r'data-compare-max="\d+"', body), f"{path} does not publish it"


def test_the_feed_is_discoverable_from_the_head(real_app):
    """Readers and browser extensions scan <head> and nothing else, so a
    link in the body is a link nobody follows."""
    body = real_app.test_client().get("/").get_data(as_text=True)
    head = body[:body.index("</head>")]

    assert "changelog.atom" in head, "the autodiscovery link is outside <head>"
