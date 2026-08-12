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
import threading
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

import config
from models import Agent

logger = logging.getLogger(__name__)

admin_bp = Blueprint('admin', __name__, url_prefix='/api/admin')

EDITABLE_FIELDS = ("name", "description", "category", "tech_stack",
                   "github_stars", "url", "use_case")

# Every edit is a read-modify-write of the whole catalogue. Flask's dev server
# is threaded, so two concurrent edits would both read the same list and the
# second write would silently discard the first — with both returning success.
# One process-wide lock is enough here: this is a single-process local tool,
# and the alternative (per-record locking or a real database) is far more
# machinery than a hand-edited JSON file warrants.
_write_lock = threading.Lock()


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


def _append_audit(action, name, before=None, after=None):
    """Record a catalogue change as one JSON line.

    Edits overwrite agents.json in place, so without this a mistaken change is
    both untraceable and unrecoverable. One line per change keeps it appendable
    and greppable, and holding the previous record means a bad edit can be
    undone by hand.

    Best-effort: an audit failure must not block the edit that succeeded.
    """
    if not config.AUDIT_LOG_PATH:
        return
    entry = {
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "action": action,
        "name": name,
    }
    if before is not None:
        entry["before"] = before
    if after is not None:
        entry["after"] = after

    try:
        path = str(config.AUDIT_LOG_PATH)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError as e:
        logger.warning("Could not write the audit log at %s: %s", config.AUDIT_LOG_PATH, e)


def read_audit(limit=50):
    """Return the most recent audit entries, newest first."""
    path = str(config.AUDIT_LOG_PATH or "")
    if not path or not os.path.exists(path):
        return []
    try:
        with open(path) as f:
            lines = f.readlines()
    except OSError as e:
        logger.warning("Could not read the audit log: %s", e)
        return []

    entries = []
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # a truncated line should not hide the rest
        if len(entries) >= limit:
            break
    return entries


def _find(records, name):
    wanted = (name or "").strip().casefold()
    for index, record in enumerate(records):
        if record.get("name", "").casefold() == wanted:
            return index
    return None


@admin_bp.route('/agents', methods=['GET'])
def list_agents():
    """The catalogue exactly as it is on disk.

    The editor must not read /api/agents: that is served from the FAISS
    docstore, which carries only the fields used for search. `use_case` is
    absent there, so loading a row from it and saving would blank the field —
    a PUT replaces the whole record. It also lags unindexed edits, so a second
    edit would resubmit stale values and revert the first.
    """
    _require_enabled()
    records = load_catalogue()
    return jsonify({"agents": records, "total": len(records)}), 200


@admin_bp.route('/similar-check', methods=['POST'])
def similar_check():
    """Warn about agents already in the catalogue that resemble a draft.

    Exact-name collisions are rejected outright by validate(); this catches
    the softer case — the same tool under a different name, or a genuine
    near-duplicate. Advisory only: it returns candidates and lets the person
    decide, because "similar" is not the same as "the same".
    """
    _require_enabled()

    payload = request.get_json(silent=True) or {}
    description = (payload.get("description") or "").strip()
    name = (payload.get("name") or "").strip()
    if not (description or name):
        raise AdminError("Provide a name or description to check")

    from api import get_store

    store = get_store()
    if store.vector_store is None:
        # Nothing to compare against; not an error.
        return jsonify({"similar": [], "checked": False}), 200

    results = store.search(f"{name}. {description}".strip(". "), limit=4)

    wanted = name.casefold()
    similar = [
        {
            "name": r["name"],
            "score": round(r["score"], 4),
            "category": r["metadata"].get("category"),
            "description": r["metadata"].get("description", ""),
        }
        for r in results
        if (r["name"] or "").casefold() != wanted
        and r["score"] >= config.DUPLICATE_SCORE
    ][:3]

    return jsonify({"similar": similar, "checked": True}), 200


@admin_bp.route('/agents', methods=['POST'])
def create_agent():
    _require_enabled()
    payload = request.get_json(silent=True)
    with _write_lock:
        records = load_catalogue()
        cleaned = validate(payload, records)
        records.append(cleaned)
        save_catalogue(records)
        _append_audit("create", cleaned["name"], after=cleaned)
    logger.info("Added agent %r to the catalogue", cleaned["name"])
    return jsonify({"agent": cleaned, "total": len(records)}), 201


@admin_bp.route('/agents/<path:name>', methods=['PUT'])
def update_agent(name):
    _require_enabled()
    payload = request.get_json(silent=True)
    with _write_lock:
        records = load_catalogue()
        index = _find(records, name)
        if index is None:
            raise AdminError(f"No agent named {name!r}", status=404)

        previous = records[index]
        cleaned = validate(payload, records, original_name=previous.get("name"))
        records[index] = cleaned
        save_catalogue(records)
        _append_audit("update", cleaned["name"], before=previous, after=cleaned)
    logger.info("Updated agent %r", cleaned["name"])
    return jsonify({"agent": cleaned, "total": len(records)}), 200


@admin_bp.route('/agents/<path:name>', methods=['DELETE'])
def delete_agent(name):
    _require_enabled()
    with _write_lock:
        records = load_catalogue()
        index = _find(records, name)
        if index is None:
            raise AdminError(f"No agent named {name!r}", status=404)

        removed = records.pop(index)
        save_catalogue(records)
        _append_audit("delete", removed.get("name"), before=removed)
    logger.info("Deleted agent %r", removed.get("name"))
    return jsonify({"deleted": removed.get("name"), "total": len(records)}), 200


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


@admin_bp.route('/audit', methods=['GET'])
def audit():
    """Recent catalogue changes, newest first."""
    _require_enabled()
    try:
        limit = max(1, min(int(request.args.get("limit", 50)), 500))
    except (TypeError, ValueError) as e:
        raise AdminError("'limit' must be an integer") from e
    return jsonify({"entries": read_audit(limit)}), 200


@admin_bp.route('/undo', methods=['POST'])
def undo():
    """Reverse the most recent catalogue change.

    The audit log already stores the previous record, so undo is a matter of
    putting it back: a delete re-adds, a create removes, an update restores.
    Only the latest entry can be undone — replaying further back would need
    conflict handling that a local single-user tool does not warrant.

    The undo is itself audited, so the trail stays a complete history rather
    than quietly rewinding.
    """
    _require_enabled()

    recent = read_audit(1)
    if not recent:
        raise AdminError("There is nothing to undo.", status=404)

    entry = recent[0]
    action, name = entry.get("action"), entry.get("name")

    with _write_lock:
        records = load_catalogue()
        index = _find(records, name)

        if action == "create":
            if index is None:
                raise AdminError(f"{name!r} is already gone; nothing to undo.", status=409)
            records.pop(index)
            restored = None
        elif action == "delete":
            if index is not None:
                raise AdminError(f"{name!r} exists again; nothing to undo.", status=409)
            restored = entry.get("before")
            if not restored:
                raise AdminError("That entry has no previous version recorded.", status=422)
            records.append(restored)
        elif action == "update":
            if index is None:
                raise AdminError(f"{name!r} no longer exists; nothing to undo.", status=409)
            restored = entry.get("before")
            if not restored:
                raise AdminError("That entry has no previous version recorded.", status=422)
            records[index] = restored
        else:
            raise AdminError(f"Cannot undo a {action!r} entry.", status=422)

        save_catalogue(records)
        _append_audit("undo", name, before=entry.get("after"), after=restored)

    logger.info("Undid %s of %r", action, name)
    return jsonify({"undid": action, "name": name, "total": len(records)}), 200


@admin_bp.route('/submissions', methods=['GET'])
def list_submissions():
    """Proposals awaiting review. Reviewing is a maintainer action."""
    _require_enabled()
    import submissions

    status = (request.args.get('status') or '').strip() or None
    if status and status not in (submissions.PENDING, submissions.APPROVED, submissions.REJECTED):
        raise AdminError(f"Unknown status {status!r}")

    entries = submissions.read_all(status=status)
    return jsonify({"submissions": entries, "pending": submissions.pending_count()}), 200


@admin_bp.route('/submissions/<submission_id>/approve', methods=['POST'])
def approve_submission(submission_id):
    """Accept a proposal and add it to the catalogue.

    Goes through the same write path as a direct add — same validation, same
    lock, same audit entry — so approving cannot smuggle in a record that a
    normal edit would have rejected. The catalogue may have changed since the
    proposal was made, so a name that is now taken fails here.
    """
    _require_enabled()
    import submissions

    entry = submissions.decide(submission_id, submissions.APPROVED)
    payload = entry["agent"]

    # Everything after the decision is inside the reset: a read-only data
    # directory or a malformed catalogue would otherwise leave the proposal
    # marked approved but never added, and decide() then refuses it forever.
    try:
        with _write_lock:
            records = load_catalogue()
            cleaned = validate(payload, records)
            records.append(cleaned)
            save_catalogue(records)
    except Exception:
        submissions.decide_reset(submission_id)
        raise

    # Audited as a create, not an "approve": undo() only understands
    # create/delete/update, so a bespoke action would make this change — and
    # every earlier one behind it — permanently un-undoable.
    _append_audit("create", cleaned["name"], after=cleaned)
    logger.info("Approved submission %s (%r)", submission_id, cleaned["name"])
    return jsonify({"agent": cleaned, "total": len(records)}), 201


@admin_bp.route('/submissions/<submission_id>/reject', methods=['POST'])
def reject_submission(submission_id):
    """Decline a proposal, optionally saying why."""
    _require_enabled()
    import submissions

    payload = request.get_json(silent=True) or {}
    note = payload.get("note")
    if note is not None and not isinstance(note, str):
        raise AdminError("'note' must be a string")

    entry = submissions.decide(submission_id, submissions.REJECTED, note=note)
    return jsonify({"submission": entry}), 200


@admin_bp.route('/status', methods=['GET'])
def status():
    """Whether editing is available, and whether the index is behind."""
    import submissions
    from api import get_store

    payload = {
        "enabled": bool(config.ENABLE_ADMIN),
        "catalogue_stale": None,
        "total": 0,
        "pending_submissions": submissions.pending_count(),
    }
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
