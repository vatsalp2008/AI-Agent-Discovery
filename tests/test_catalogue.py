"""Integrity checks on data/agents.json.

The catalogue is hand-edited, so these guard the kinds of drift that are easy
to introduce and invisible at runtime: duplicate entries, a category that is
really a typo of another, or a broken link.
"""

import json
import re
from collections import Counter

import pytest

import config
from models import Agent


@pytest.fixture(scope="module")
def catalogue():
    with open(config.AGENTS_JSON) as f:
        return json.load(f)


def test_catalogue_is_a_list_of_objects(catalogue):
    assert isinstance(catalogue, list)
    assert catalogue, "the catalogue should not be empty"
    assert all(isinstance(record, dict) for record in catalogue)


def test_every_record_builds_an_agent(catalogue):
    """Anything seed.py would reject should fail here first."""
    for record in catalogue:
        Agent.from_dict(record)


def test_names_are_unique(catalogue):
    """Duplicates index twice and make lookup by name ambiguous."""
    counts = Counter(r["name"].casefold() for r in catalogue)
    assert [n for n, c in counts.items() if c > 1] == []


def test_no_blank_required_fields(catalogue):
    for record in catalogue:
        for field in ("name", "description", "category"):
            assert record.get(field, "").strip(), f"{record.get('name')}: blank {field}"


def test_urls_are_http(catalogue):
    for record in catalogue:
        url = record.get("url", "")
        if url:
            assert url.startswith(("http://", "https://")), f"{record['name']}: {url}"


def test_star_counts_are_sane(catalogue):
    for record in catalogue:
        stars = record.get("github_stars", 0)
        assert isinstance(stars, int), f"{record['name']}: stars must be an integer"
        assert stars >= 0, f"{record['name']}: negative stars"


def test_tech_stacks_are_lists_of_nonblank_strings(catalogue):
    for record in catalogue:
        stack = record.get("tech_stack", [])
        assert isinstance(stack, list), f"{record['name']}: tech_stack must be a list"
        for tech in stack:
            assert isinstance(tech, str) and tech.strip(), f"{record['name']}: blank tech entry"


def test_tech_entries_contain_no_commas(catalogue):
    """`stack` is stored comma-joined, so a comma inside an entry would split it."""
    for record in catalogue:
        for tech in record.get("tech_stack", []):
            assert "," not in tech, f"{record['name']}: '{tech}' contains a comma"


def test_no_category_is_a_near_duplicate_of_another(catalogue):
    """Catches 'Task Automation' sitting alongside 'Automation'."""
    categories = sorted({r["category"] for r in catalogue})
    for i, first in enumerate(categories):
        for second in categories[i + 1:]:
            a, b = first.casefold(), second.casefold()
            assert not (a in b or b in a), (
                f"'{first}' and '{second}' look like the same category split in two"
            )


def test_categories_are_title_case(catalogue):
    for category in {r["category"] for r in catalogue}:
        assert category == category.strip()
        assert re.match(r"^[A-Z]", category), f"{category!r} should start with a capital"


def test_every_page_route_has_a_template(catalogue):
    """A route rendering a template that does not exist 500s at request time."""
    import re

    import config

    app_source = (config.PACKAGE_DIR / "frontend" / "app.py").read_text()
    templates = config.PACKAGE_DIR / "frontend" / "templates"

    referenced = set(re.findall(r"render_template\('([^']+)'", app_source))
    assert referenced, "no templates referenced; the regex is wrong"

    missing = [name for name in referenced if not (templates / name).exists()]
    assert not missing, f"routes render missing templates: {missing}"


def test_every_template_script_exists(catalogue):
    """A <script src> pointing nowhere fails silently in the browser."""
    import re

    import config

    static = config.PACKAGE_DIR / "frontend" / "static"
    templates = config.PACKAGE_DIR / "frontend" / "templates"

    missing = []
    for template in templates.glob("*.html"):
        for src in re.findall(r'<script src="/static/([^"]+)"', template.read_text()):
            if not (static / src).exists():
                missing.append(f"{template.name} -> {src}")
    assert not missing, f"templates reference missing scripts: {missing}"


def test_every_template_stylesheet_exists(catalogue):
    import re

    import config

    static = config.PACKAGE_DIR / "frontend" / "static"
    templates = config.PACKAGE_DIR / "frontend" / "templates"

    missing = []
    for template in templates.glob("*.html"):
        for href in re.findall(r'<link[^>]*href="/static/([^"]+)"', template.read_text()):
            if not (static / href).exists():
                missing.append(f"{template.name} -> {href}")
    assert not missing, f"templates reference missing assets: {missing}"
