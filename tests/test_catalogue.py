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


def test_readme_documents_every_api_route(catalogue):
    """A route absent from the README is one nobody will find."""
    import re

    import config

    api_source = (config.PACKAGE_DIR / "backend" / "api.py").read_text()
    admin_source = (config.PACKAGE_DIR / "backend" / "admin.py").read_text()
    readme = (config.REPO_ROOT / "README.md").read_text()

    routes = set()
    for source, prefix in ((api_source, "/api"), (admin_source, "/api/admin")):
        for rule in re.findall(r"@\w+_bp\.route\('([^']+)'", source):
            # Strip Flask's converters: <path:name> -> <name>
            routes.add(prefix + re.sub(r"<[^:>]+:([^>]+)>", r"<\1>", rule))

    missing = []
    for route in routes:
        # The README may write the path with or without the parameter.
        base = route.split("<")[0].rstrip("/")
        if base and base not in readme:
            missing.append(route)
    assert not missing, f"README does not mention: {sorted(missing)}"


def test_readme_agent_count_matches_the_catalogue(catalogue):
    """A stale count in the README is a small lie that compounds."""
    import re

    import config

    readme = (config.REPO_ROOT / "README.md").read_text()
    claimed = re.search(r"Curated collection of (\d+) AI agents", readme)
    assert claimed, "the README no longer states an agent count"
    assert int(claimed.group(1)) == len(catalogue), (
        f"README claims {claimed.group(1)} agents, catalogue has {len(catalogue)}"
    )


def test_every_make_target_referenced_in_docs_exists(catalogue):
    import re

    import config

    makefile = (config.REPO_ROOT / "Makefile").read_text()
    targets = set(re.findall(r"^([a-z][a-z-]*):", makefile, re.M))

    for doc in ("README.md", "CONTRIBUTING.md"):
        text = (config.REPO_ROOT / doc).read_text()
        for target in re.findall(r"`make ([a-z][a-z-]*)`", text):
            assert target in targets, f"{doc} references `make {target}`, which does not exist"


def test_stylesheet_has_responsive_breakpoints(catalogue):
    """The layout had none, so every fixed min-width forced a phone to scroll."""
    import re

    import config

    css = (config.PACKAGE_DIR / "frontend" / "static" / "css" / "style.css").read_text()
    widths = re.findall(r"@media\s*\(\s*max-width:\s*(\d+)px", css)
    assert widths, "no max-width breakpoints"
    assert any(int(w) <= 500 for w in widths), "nothing targets phone widths"


def test_stylesheet_braces_are_balanced(catalogue):
    """A stray brace silently disables everything after it."""
    import config

    css = (config.PACKAGE_DIR / "frontend" / "static" / "css" / "style.css").read_text()
    assert css.count("{") == css.count("}")


def test_every_css_class_used_in_js_exists(catalogue):
    """A typo'd class name renders unstyled and is easy to miss."""
    import re

    import config

    static = config.PACKAGE_DIR / "frontend" / "static"
    css = (static / "css" / "style.css").read_text()
    defined = set(re.findall(r"\.([a-z][a-z0-9-]+)", css))

    missing = {}
    for script in (static / "js").glob("*.js"):
        source = script.read_text()
        # className = 'x' and className = `x` forms used throughout.
        for name in re.findall(r"className\s*=\s*['\"]([a-z][a-z0-9 -]*)['\"]", source):
            for cls in name.split():
                if cls not in defined:
                    missing.setdefault(script.name, set()).add(cls)

    assert not missing, f"classes used in JS but absent from the stylesheet: {missing}"


def test_descriptions_carry_enough_signal(catalogue):
    """The description is what gets embedded, so a tagline is not enough.

    "Your Second Brain, empowered by Generative AI" told the index nothing
    about files, documents or search, so Quivr did not surface for its own
    use case.
    """
    thin = [r["name"] for r in catalogue if len(r.get("description", "")) < 60]
    assert not thin, f"descriptions too short to embed usefully: {thin}"


def test_no_two_agents_share_a_description(catalogue):
    """Identical text would make two agents indistinguishable to search."""
    from collections import Counter

    counts = Counter(r.get("description", "") for r in catalogue)
    assert [d for d, n in counts.items() if n > 1] == []


def test_every_agent_has_a_use_case(catalogue):
    missing = [r["name"] for r in catalogue if not r.get("use_case", "").strip()]
    assert not missing, f"missing use_case: {missing}"


def test_every_agent_has_a_tech_stack(catalogue):
    missing = [r["name"] for r in catalogue if not r.get("tech_stack")]
    assert not missing, f"missing tech_stack: {missing}"


def test_no_category_holds_a_single_agent(catalogue):
    """A category of one is usually a mis-file or an unfinished addition.

    "Task Automation" held only BabyAGI and belonged in "Autonomous Agent";
    "Robotics" held only LeRobot until the category was filled out. Either
    fold it into a neighbour or add its siblings.
    """
    from collections import Counter

    counts = Counter(r["category"] for r in catalogue)
    singletons = [name for name, count in counts.items() if count == 1]
    assert not singletons, f"categories with one agent: {singletons}"


def test_built_in_samples_have_unique_names():
    """SAMPLE_AGENTS seeds a fresh checkout, so a duplicate there would index
    the same agent twice. The catalogue check above does not cover it —
    a duplicate was added and went unnoticed until a seed produced two rows."""
    from collections import Counter

    import scraper

    counts = Counter(a.name.casefold() for a in scraper.SAMPLE_AGENTS)
    assert [n for n, c in counts.items() if c > 1] == []


def test_built_in_samples_are_valid_agents():
    """They bypass the admin validation path, so check them directly."""
    import scraper

    for agent in scraper.SAMPLE_AGENTS:
        assert agent.name.strip(), "an unnamed sample agent"
        assert agent.description.strip(), f"{agent.name}: no description"
        assert agent.category.strip(), f"{agent.name}: no category"
        for tech in agent.tech_stack:
            assert "," not in tech, f"{agent.name}: comma in tech entry {tech!r}"
