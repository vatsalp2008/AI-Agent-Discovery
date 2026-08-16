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


def test_docs_cover_every_api_route(catalogue):
    """A route documented nowhere is one nobody will find.

    Checked across the README and docs/API.md: the reference moved out of the
    README when it passed 880 lines, so either is a valid home.
    """
    import re

    import config

    api_source = (config.PACKAGE_DIR / "backend" / "api.py").read_text()
    admin_source = (config.PACKAGE_DIR / "backend" / "admin.py").read_text()
    docs = ((config.REPO_ROOT / "README.md").read_text()
            + (config.REPO_ROOT / "docs" / "API.md").read_text())

    routes = set()
    for source, prefix in ((api_source, "/api"), (admin_source, "/api/admin")):
        for rule in re.findall(r"@\w+_bp\.route\('([^']+)'", source):
            # Strip Flask's converters: <path:name> -> <name>
            routes.add(prefix + re.sub(r"<[^:>]+:([^>]+)>", r"<\1>", rule))

    missing = []
    for route in routes:
        # The README may write the path with or without the parameter.
        base = route.split("<")[0].rstrip("/")
        if base and base not in docs:
            missing.append(route)
    assert not missing, f"neither README nor docs/API.md mentions: {sorted(missing)}"


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
    import submissions

    floor = submissions.MIN_DESCRIPTION
    thin = [r["name"] for r in catalogue if len(r.get("description", "")) < floor]
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


def test_every_script_is_loaded_by_some_template(catalogue):
    """A JS file no template loads is dead code; the reverse is a 404.

    Both are silent — the page just misses a feature, and nothing fails.
    """
    import re

    import config

    static = config.PACKAGE_DIR / "frontend" / "static" / "js"
    templates = config.PACKAGE_DIR / "frontend" / "templates"

    loaded = set()
    for template in templates.glob("*.html"):
        loaded |= set(re.findall(r'<script src="/static/js/([^"]+)"', template.read_text()))

    present = {p.name for p in static.glob("*.js")}
    assert not (present - loaded), f"scripts no template loads: {sorted(present - loaded)}"
    assert not (loaded - present), f"templates load missing scripts: {sorted(loaded - present)}"


def test_scripts_load_after_their_dependencies(catalogue):
    """A global used before its defining file is loaded is undefined at runtime.

    main.js calls AgentsApi and SearchState; compare.js and category.js call
    AgentsApi. Order in the template is what makes that work.

    Usage guarded by `typeof X === 'undefined'` is exempt: that is how an
    optional dependency is declared. agent-card.js uses Collections that way,
    so it renders a save control on pages that load collections.js and skips
    it on those that do not.
    """
    import re

    import config

    templates = config.PACKAGE_DIR / "frontend" / "templates"
    base = (templates / "base.html").read_text()

    provides = {
        "agents-api.js": "AgentsApi",
        "search-state.js": "SearchState",
        "agent-card.js": "AgentCard",
        "collections.js": "Collections",
        "suggest.js": "Suggest",
        "dashboard-stats.js": "DashboardStats",
        "export-results.js": "ExportResults",
    }

    problems = []
    for template in templates.glob("*.html"):
        if template.name == "base.html":
            continue
        # base.html's scripts load first, then the page's own block.
        order = (re.findall(r'<script src="/static/js/([^"]+)"', base)
                 + re.findall(r'<script src="/static/js/([^"]+)"', template.read_text()))

        available = set()
        for script in order:
            source = (config.PACKAGE_DIR / "frontend" / "static" / "js" / script).read_text()
            for dependency, global_name in provides.items():
                if dependency == script:
                    continue
                if global_name in available:
                    continue
                guarded = re.search(rf"typeof\s+{global_name}\s*===?\s*['\"]undefined", source)
                if re.search(rf"\b{global_name}\.", source) and not guarded:
                    problems.append(f"{template.name}: {script} uses {global_name} before it loads")
            if script in provides:
                available.add(provides[script])

    assert not problems, problems


def test_the_readme_stays_navigable(catalogue):
    """It reached 881 lines before the API reference moved to docs/API.md.

    Not a style rule: a README nobody scrolls to the end of is one where the
    setup instructions stop being found.
    """
    import config

    lines = (config.REPO_ROOT / "README.md").read_text().count("\n")
    assert lines < 700, f"README is {lines} lines; consider moving a section into docs/"


def _markdown_files():
    """Every markdown file that is ours to keep correct."""
    import config

    return [config.REPO_ROOT / "README.md",
            config.REPO_ROOT / "CONTRIBUTING.md",
            *sorted((config.REPO_ROOT / "docs").glob("*.md"))]


def test_docs_links_resolve(catalogue):
    """A broken relative link in the docs is invisible until someone clicks."""
    import re

    # Every markdown file, rather than a list to keep in step — a new doc
    # was going unchecked until someone remembered to add it here.
    for source in _markdown_files():
        text = source.read_text()
        for target in re.findall(r"\]\((?!https?://|#)([^)#]+)", text):
            resolved = (source.parent / target).resolve()
            assert resolved.exists(), f"{source.name} links to missing {target}"


def test_doc_contents_anchors_resolve(catalogue):
    """A table of contents pointing at headings that do not exist is worse
    than none: it looks navigable and is not."""
    import re

    def slug(heading):
        """GitHub's anchor for a heading.

        The emoji is removed but the space after it is not, so "## 🚀 Features"
        anchors as "#-features" with a leading hyphen. Stripping first would
        make this test demand anchors that are broken on GitHub — which is
        how it passed while docs/CATALOGUE.md was correct and it was not.
        """
        cleaned = re.sub(r"[^\w\s-]", "", heading.lower()).rstrip()
        return re.sub(r"\s+", "-", cleaned)

    dangling = {}
    for source in _markdown_files():
        text = source.read_text()
        headings = {slug(h) for h in re.findall(r"^#{2,4} (.+)$", text, flags=re.M)}
        anchors = set(re.findall(r"\]\(#([^)]+)\)", text))
        if anchors - headings:
            dangling[source.name] = sorted(anchors - headings)

    assert not dangling, f"dangling anchors: {dangling}"


def test_ci_imports_every_backend_module(catalogue):
    """A module absent from the import check can break without CI noticing —
    the unit tests stub most of them, so a bad import only shows at runtime."""
    import re

    import config

    workflow = (config.REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text()
    checked = set(re.search(r'python -c "import ([^"]+)"', workflow).group(1).split(", "))

    backend = config.PACKAGE_DIR / "backend"
    present = {p.stem for p in backend.glob("*.py")} - {"__init__", "logging_setup"}

    assert not (present - checked), f"CI does not import: {sorted(present - checked)}"


def test_ci_imports_every_top_level_script(catalogue):
    """The scripts have no unit tests that import them, and `compileall`
    only proves they parse. A bad import in one shows up when a scheduled
    job runs it, which is days later and unattended."""
    import re

    import config

    workflow = (config.REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text()
    checked = set()
    for group in re.findall(r'python -c "import ([^"]+)"', workflow):
        checked |= {name.strip() for name in group.split(",")}

    present = {p.stem for p in config.PACKAGE_DIR.glob("*.py")} - {"__init__"}

    assert not (present - checked), f"CI does not import: {sorted(present - checked)}"


def test_every_agent_would_still_be_accepted_today(catalogue):
    """The limits on /api/submissions apply to the editor too. Tightening one
    below what the catalogue already holds would make existing agents
    un-editable — a save would fail on a record nobody touched."""
    import admin

    over = []
    for record in catalogue:
        for field, limit in admin.FIELD_LIMITS.items():
            if len(str(record.get(field, ""))) > limit:
                over.append(f"{record['name']}.{field}")
        stack = record.get("tech_stack", [])
        if len(stack) > admin.MAX_TECH_STACK:
            over.append(f"{record['name']}.tech_stack")
        over += [f"{record['name']}.tech_stack[{t}]"
                 for t in stack if len(t) > admin.MAX_TECH_LENGTH]

    assert not over, f"these fields exceed the validation limits: {over}"


def test_every_page_that_reports_an_outcome_announces_it():
    """A result that only appears visually is invisible to a screen reader.

    The live region also has to be present and visible from the start:
    content added to a `hidden` element is not announced, which is exactly
    the bug the submit page shipped with.
    """
    templates = config.PACKAGE_DIR / "frontend" / "templates"
    # Every page template rather than a list to keep in step: a new page was
    # going unchecked until somebody remembered to add it here, which is
    # exactly when the check is worth the most.
    reporting = sorted(p.name for p in templates.glob("*.html")
                       if p.name != "base.html")

    missing = []
    for name in reporting:
        text = (templates / name).read_text()
        regions = re.findall(r"<[^>]*(?:aria-live|role=\"status\")[^>]*>", text)
        if not regions:
            missing.append(f"{name}: no live region")
        elif all("hidden" in tag for tag in regions):
            missing.append(f"{name}: every live region is hidden")

    assert not missing, missing


def test_workflows_only_run_scripts_that_exist():
    """A workflow naming a renamed script fails on a schedule, where nobody
    is watching — the weekly job just goes red weeks later."""
    import re

    workflows = config.REPO_ROOT / ".github" / "workflows"
    referenced = set()
    for workflow in workflows.glob("*.yml"):
        referenced |= {(workflow.name, script) for script
                       in re.findall(r"python (ai-agent-discovery/[\w./-]+\.py)",
                                     workflow.read_text())}

    assert referenced, "no scripts referenced; the regex is wrong"
    missing = [f"{w}: {s}" for w, s in referenced
               if not (config.REPO_ROOT / s).exists()]
    assert not missing, f"workflows run missing scripts: {missing}"


def test_every_scheduled_workflow_can_also_be_run_by_hand():
    """A cron-only workflow cannot be tested without waiting a week, and
    cannot be re-run after fixing whatever made it fail."""
    import yaml

    workflows = config.REPO_ROOT / ".github" / "workflows"
    missing = []
    for workflow in workflows.glob("*.yml"):
        # `on` is parsed as the boolean True by YAML 1.1, which is what
        # PyYAML implements.
        triggers = yaml.safe_load(workflow.read_text()).get(True, {})
        if "schedule" in triggers and "workflow_dispatch" not in triggers:
            missing.append(workflow.name)

    assert not missing, f"scheduled but not manually runnable: {missing}"


def test_no_page_reports_into_a_hidden_element():
    """The bug three pages shipped with: a message written into a `hidden`
    paragraph is styled correctly, reads correctly, and is never announced —
    a screen-reader user got nothing from a save, a delete or a submission.

    The fix is one always-present live region per page, which is why the
    check is "no hidden result-message" rather than "has a live region".
    """
    import re

    templates = config.PACKAGE_DIR / "frontend" / "templates"

    offenders = []
    for template in templates.glob("*.html"):
        for tag in re.findall(r"<(?:p|div)[^>]*>", template.read_text()):
            if "result-message" in tag and "hidden" in tag:
                offenders.append(f"{template.name}: {tag}")

    assert not offenders, offenders


def test_no_source_file_contains_a_control_character():
    """A stray NUL makes git treat a text file as binary.

    saved-searches.js shipped with one: `git diff` showed "Binary files
    differ", so the file had no reviewable diff and no line-wise blame. It
    was invisible in the editor, and it was doing real work — separating the
    two halves of a cache key — so removing it needed a deliberate
    replacement rather than a delete.
    """
    import subprocess

    # Only files we actually track: a vendored venv contains third-party
    # fixtures that are deliberately not UTF-8, and they are not ours to fix.
    listed = subprocess.run(["git", "ls-files", "-z"], cwd=config.REPO_ROOT,
                            capture_output=True, text=True, check=True)
    suffixes = {".py", ".js", ".css", ".html", ".md", ".json", ".yml"}
    allowed = {"\t", "\n", "\r"}

    offenders = []
    for name in listed.stdout.split("\0"):
        path = config.REPO_ROOT / name
        if not name or path.suffix not in suffixes or not path.exists():
            continue
        try:
            text = path.read_text()
        except (UnicodeDecodeError, OSError):
            offenders.append(f"{name}: not readable as text")
            continue
        bad = {c for c in text if ord(c) < 32 and c not in allowed}
        if bad:
            offenders.append(f"{name}: {[hex(ord(c)) for c in sorted(bad)]}")

    assert not offenders, offenders


def test_accent_text_meets_contrast_in_both_themes():
    """Accent used as text sits on the card background at 0.8rem, so it
    needs the 4.5:1 WCAG AA ratio for body text. The fill colour is 3.98:1
    in dark mode, which is why --accent-text exists separately.
    """
    import re

    def luminance(hex_colour):
        channels = []
        for i in (0, 2, 4):
            value = int(hex_colour.lstrip("#")[i:i + 2], 16) / 255
            channels.append(value / 12.92 if value <= 0.03928
                            else ((value + 0.055) / 1.055) ** 2.4)
        return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]

    def contrast(a, b):
        high, low = sorted((luminance(a), luminance(b)), reverse=True)
        return (high + 0.05) / (low + 0.05)

    css = (config.PACKAGE_DIR / "frontend" / "static" / "css" / "style.css").read_text()

    def value(name, after):
        block = css[css.index(after):]
        return re.search(rf"--{name}: (#[0-9a-fA-F]{{6}})", block).group(1)

    pairs = [
        ("dark", value("accent-text", ":root,"), value("card-bg", ":root,")),
        ("light", value("accent-text", '[data-theme="light"]'),
                  value("card-bg", '[data-theme="light"]')),
    ]
    for theme, text, background in pairs:
        ratio = contrast(text, background)
        assert ratio >= 4.5, f"{theme}: accent text on card is {ratio:.2f}:1, below AA"

    # The split only helps if text actually uses the text token. The lookbehind
    # excludes border-color and background-color, which keep --accent-color.
    leaked = re.findall(r"(?<![-a-z])color: var\(--accent-color\)", css)
    assert not leaked, f"{len(leaked)} text colour(s) still use the fill accent"


def test_every_doc_is_reachable_from_the_readme():
    """A doc nobody links to is a doc nobody reads.

    The README is the only entry point most people have, so moving a section
    into docs/ only works if the pointer goes with it — and the pointer is
    the easiest half to forget.
    """
    readme = (config.REPO_ROOT / "README.md").read_text()

    unlinked = [path.name for path in sorted((config.REPO_ROOT / "docs").glob("*.md"))
                if f"docs/{path.name}" not in readme]
    assert not unlinked, f"docs the README never links to: {unlinked}"


def test_every_script_is_runnable_from_the_makefile():
    """A script with no `make` target is one nobody discovers.

    Matched on the filename rather than the target name: the targets are
    hyphenated (`make check-links` runs `check_links.py`), and three scripts
    were added this week — each one is a chance to forget.
    """
    makefile = (config.REPO_ROOT / "Makefile").read_text()

    scripts = sorted(p.name for p in config.PACKAGE_DIR.glob("*.py")
                     if p.stem != "__init__")
    missing = [name for name in scripts if name not in makefile]

    assert scripts, "no scripts found; the glob is wrong"
    assert not missing, f"no make target runs: {missing}"


def test_project_health_is_surfaced_wherever_an_agent_is_rendered():
    """The status field only earns its keep if it is visible.

    It was added to four surfaces one at a time — the card, the detail page,
    the comparison table and the MCP result — and each addition was a
    separate chance to forget one. A place that renders an agent without it
    presents an abandoned tool as a live one.
    """
    js = config.PACKAGE_DIR / "frontend" / "static" / "js"
    renderers = {
        "agent-card.js": "the search result card",
        "agent.js": "the agent detail page",
        "compare.js": "the comparison table",
    }

    missing = [f"{name} ({what})" for name, what in renderers.items()
               if "status" not in (js / name).read_text()]
    assert not missing, f"these render an agent without its health: {missing}"

    mcp = (config.PACKAGE_DIR / "mcp_server.py").read_text()
    assert "status" in mcp, "MCP results omit project health"
