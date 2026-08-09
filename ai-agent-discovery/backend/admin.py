"""Write access to the agent catalogue.

The README tells people to hand-edit data/agents.json, which is fine for a
one-off but easy to get wrong: a stray comma breaks seeding, and there is no
feedback until you re-run it. These endpoints do the same edits with
validation and a clear error.

**Off by default.** This is the only part of the app that writes anything, and
it takes no authentication, so enabling it on a reachable interface would let
anyone rewrite the catalogue. Set ENABLE_ADMIN=true to turn it on, and keep
HOST bound to localhost.

Writes go to agents.json only. The FAISS index is rebuilt separately via
/api/admin/reindex, so a batch of edits costs one re-embed rather than one per
change.
"""

import json
import logging
import os

from flask import Blueprint, jsonify, request

import config
from models import Agent

logger = logging.getLogger(__name__)

admin_bp = Blueprint('admin', __name__, url_prefix='/api/admin')

EDITABLE_FIELDS = ("name", "description", "category", "tech_stack",
                   "github_stars", "url", "use_case")


class AdminError(Exception):
    """A rejected edit, reported to the client as a 4xx."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _require_enabled():
    if not config.ENABLE_ADMIN:
        raise AdminError(
            "Catalogue editing is disabled. Set ENABLE_ADMIN=true to enable it.",
            status=403,
        )


def load_catalogue():
    """Read agents.json, or start an empty catalogue if it does not exist."""
    if not os.path.exists(config.AGENTS_JSON):
        return []
    try:
        with open(config.AGENTS_JSON) as f:
            records = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise AdminError(f"Could not read the catalogue: {e}", status=500) from e

    if not isinstance(records, list):
        raise AdminError("The catalogue must be a JSON array", status=500)
    return records


def save_catalogue(records):
    """Write agents.json atomically, so a crash cannot truncate it."""
    try:
        # AGENTS_JSON is separately configurable, so it need not sit inside
        # DATA_DIR; create the directory it actually points at.
        os.makedirs(os.path.dirname(str(config.AGENTS_JSON)) or ".", exist_ok=True)
        tmp = f"{config.AGENTS_JSON}.tmp"
        with open(tmp, "w") as f:
            json.dump(records, f, indent=2)
            f.write("\n")
        os.replace(tmp, config.AGENTS_JSON)
    except OSError as e:
        raise AdminError(f"Could not write the catalogue: {e}", status=500) from e


def validate(record, existing, original_name=None):
    """Return a cleaned record, or raise AdminError explaining what is wrong."""
    if not isinstance(record, dict):
        raise AdminError("Expected a JSON object describing an agent")

    unknown = set(record) - set(EDITABLE_FIELDS)
    if unknown:
        raise AdminError(f"Unknown field(s): {', '.join(sorted(unknown))}")

    cleaned = {}
    for field in ("name", "description", "category"):
        value = record.get(field)
        if not isinstance(value, str) or not value.strip():
            raise AdminError(f"'{field}' is required")
        cleaned[field] = value.strip()

    stack = record.get("tech_stack", [])
    if not isinstance(stack, list) or not all(isinstance(t, str) for t in stack):
        raise AdminError("'tech_stack' must be a list of strings")
    # Commas would split one entry into two, since stack is stored joined.
    if any("," in t for t in stack):
        raise AdminError("'tech_stack' entries must not contain commas")
    cleaned["tech_stack"] = [t.strip() for t in stack if t.strip()]

    stars = record.get("github_stars", 0)
    if isinstance(stars, bool) or not isinstance(stars, int) or stars < 0:
        raise AdminError("'github_stars' must be a non-negative integer")
    cleaned["github_stars"] = stars

    url = record.get("url", "")
    if not isinstance(url, str):
        raise AdminError("'url' must be a string")
    url = url.strip()
    if url and not url.startswith(("http://", "https://")):
        raise AdminError("'url' must start with http:// or https://")
    cleaned["url"] = url

    use_case = record.get("use_case", "")
    if not isinstance(use_case, str):
        raise AdminError("'use_case' must be a string")
    cleaned["use_case"] = use_case.strip()

    # Names identify agents everywhere else, so they have to stay unique.
    # Existing records are read from a hand-editable file, so they may be
    # malformed; use .get and skip anything unusable rather than raising a
    # 500 from inside what is meant to be a validation routine.
    wanted = cleaned["name"].casefold()
    for other in existing:
        if not isinstance(other, dict):
            continue
        other_name = other.get("name")
        if not isinstance(other_name, str):
            continue
        if other_name.casefold() == wanted and other_name != original_name:
            raise AdminError(f"An agent named {cleaned['name']!r} already exists", status=409)

    # Fails for the same reasons seeding would, but here rather than later.
    Agent.from_dict(cleaned)
    return cleaned


def _find(records, name):
    wanted = (name or "").strip().casefold()
    for index, record in enumerate(records):
        if record.get("name", "").casefold() == wanted:
            return index
    return None


@admin_bp.route('/agents', methods=['POST'])
def create_agent():
    _require_enabled()
    records = load_catalogue()
    cleaned = validate(request.get_json(silent=True), records)
    records.append(cleaned)
    save_catalogue(records)
    logger.info("Added agent %r to the catalogue", cleaned["name"])
    return jsonify({"agent": cleaned, "total": len(records)}), 201


@admin_bp.route('/agents/<path:name>', methods=['PUT'])
def update_agent(name):
    _require_enabled()
    records = load_catalogue()
    index = _find(records, name)
    if index is None:
        raise AdminError(f"No agent named {name!r}", status=404)

    cleaned = validate(request.get_json(silent=True), records, original_name=records[index]["name"])
    records[index] = cleaned
    save_catalogue(records)
    logger.info("Updated agent %r", cleaned["name"])
    return jsonify({"agent": cleaned, "total": len(records)}), 200


@admin_bp.route('/agents/<path:name>', methods=['DELETE'])
def delete_agent(name):
    _require_enabled()
    records = load_catalogue()
    index = _find(records, name)
    if index is None:
        raise AdminError(f"No agent named {name!r}", status=404)

    removed = records.pop(index)
    save_catalogue(records)
    logger.info("Deleted agent %r", removed["name"])
    return jsonify({"deleted": removed["name"], "total": len(records)}), 200


@admin_bp.route('/reindex', methods=['POST'])
def reindex():
    """Rebuild the FAISS index from the current catalogue.

    Separate from the edit endpoints on purpose: re-embedding every agent
    takes seconds, so a batch of edits should cost one rebuild rather than one
    per change. Rebuilds rather than appends, so this cannot duplicate agents.
    """
    _require_enabled()

    from api import get_store
    from scraper import CatalogueError, load_agents

    try:
        agents = load_agents()
    except CatalogueError as e:
        raise AdminError(str(e), status=400) from e

    store = get_store()
    try:
        store.replace_agents(agents)
    except Exception as e:
        logger.exception("Reindex failed")
        raise AdminError(f"Could not rebuild the index: {e}", status=500) from e

    stats = store.get_stats()
    logger.info("Reindexed %d agents", stats.get("count", 0))
    return jsonify({
        "indexed": stats.get("count", 0),
        "built_at": stats.get("built_at"),
    }), 200


@admin_bp.route('/status', methods=['GET'])
def status():
    """Whether editing is available, and whether the index is behind."""
    from api import get_store

    payload = {"enabled": bool(config.ENABLE_ADMIN), "catalogue_stale": None, "total": 0}
    try:
        payload["total"] = len(load_catalogue())
        payload["catalogue_stale"] = get_store().catalogue_is_stale
    except AdminError:
        pass
    return jsonify(payload), 200


def register_error_handler(app):
    @app.errorhandler(AdminError)
    def handle(e):
        return jsonify({"error": str(e)}), e.status

    return app
