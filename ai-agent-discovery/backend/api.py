import hashlib
import json
import logging
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from flask import Blueprint, jsonify, make_response, request
from werkzeug.exceptions import HTTPException

import config
import generation
import rate_limit
from vectorstore import VectorStore

logger = logging.getLogger(__name__)

api_bp = Blueprint('api', __name__, url_prefix='/api')

_store = None


def get_store() -> VectorStore:
    """Return the shared VectorStore, constructing it on first use.

    Building the store contacts Ollama and reads the FAISS index, so it is
    deferred until a request actually needs it. Otherwise importing this
    module — during tests, or when Ollama simply is not running yet — would
    fail before the app can serve anything.
    """
    global _store
    if _store is None:
        _store = VectorStore()
    return _store


def set_store(store) -> None:
    """Override the shared store. Used by tests."""
    global _store
    _store = store


def register_error_handlers(app):
    """Return JSON (not Flask's HTML error page) for failures under /api.

    Routing errors are raised before a blueprint is selected, so these must be
    registered on the app rather than the blueprint. Non-API paths keep the
    default HTML behaviour so the browser UI is unaffected.
    """
    prefix = api_bp.url_prefix + '/'

    def is_api_request():
        return request.path.startswith(prefix)

    @app.errorhandler(404)
    def handle_not_found(e):
        if is_api_request():
            return jsonify({"error": "Not found", "path": request.path}), 404
        return e.get_response()

    @app.errorhandler(405)
    def handle_method_not_allowed(e):
        if is_api_request():
            return jsonify({"error": f"Method {request.method} not allowed for {request.path}"}), 405
        return e.get_response()

    @app.errorhandler(413)
    def handle_too_large(e):
        # Werkzeug's default wording does not say what the limit is, and the
        # body is rejected before any route runs, so the client would
        # otherwise have no way to tell how much to trim.
        if is_api_request():
            return jsonify({
                "error": "Request body too large",
                "max_bytes": config.MAX_REQUEST_BYTES,
            }), 413
        return e.get_response()

    @app.errorhandler(Exception)
    def handle_unexpected(e):
        # Let real HTTP errors keep their status; only 500s land here.
        if isinstance(e, HTTPException):
            if is_api_request():
                return jsonify({"error": e.description}), e.code
            return e.get_response()
        logger.exception("Unhandled error serving %s", request.path)
        if is_api_request():
            return jsonify({"error": "Internal server error"}), 500
        raise e

    return app


def _etag_response(payload, status=200):
    """Return `payload` as JSON with an ETag, or 304 if the client has it.

    The catalogue only changes when the index is rebuilt, but the dashboard
    and comparison pages re-request it on every navigation. An ETag lets the
    browser skip the transfer entirely once it has a copy.

    Weak validators would be enough here, but a strong one is cheap: the body
    is deterministic, so hashing it is exact rather than a guess.
    """
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    etag = hashlib.sha256(body.encode("utf-8")).hexdigest()[:32]

    if request.if_none_match and etag in request.if_none_match:
        response = make_response("", 304)
    else:
        response = make_response(jsonify(payload), status)

    response.set_etag(etag)
    # Revalidate every time rather than serving a stale catalogue from cache;
    # the round trip is cheap once the body is skipped.
    response.headers["Cache-Control"] = "no-cache"
    return response


class BadRequest(Exception):
    """Raised when the client sends an unusable payload."""


def _parse_query(payload):
    """Validate and normalize the search query from a request body."""
    if not isinstance(payload, dict):
        raise BadRequest("Request body must be a JSON object")

    query = payload.get('query')
    if query is None or (isinstance(query, str) and not query.strip()):
        raise BadRequest("No query provided")
    if not isinstance(query, str):
        raise BadRequest("'query' must be a string")

    query = query.strip()
    if len(query) > config.MAX_QUERY_LENGTH:
        raise BadRequest(f"'query' must be at most {config.MAX_QUERY_LENGTH} characters")
    return query


def _parse_limit(payload):
    """Validate the optional result limit, clamped to the configured maximum."""
    raw = payload.get('limit', config.SEARCH_DEFAULT_LIMIT)
    try:
        limit = int(raw)
    except (TypeError, ValueError) as e:
        raise BadRequest("'limit' must be an integer") from e
    if limit < 1:
        raise BadRequest("'limit' must be at least 1")
    return min(limit, config.SEARCH_MAX_LIMIT)


def _parse_summarize(payload):
    """Validate the optional 'summarize' flag."""
    value = payload.get('summarize', False)
    if isinstance(value, bool):
        return value
    raise BadRequest("'summarize' must be a boolean")


def _parse_maintained(payload):
    """Validate the optional "hide abandoned projects" flag."""
    value = payload.get('maintained', False)
    if isinstance(value, bool):
        return value
    raise BadRequest("'maintained' must be a boolean")


def _parse_min_score(payload):
    """Validate the optional hard score filter."""
    raw = payload.get('min_score')
    if raw is None:
        return None
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise BadRequest("'min_score' must be a number")
    if not 0.0 <= raw <= 1.0:
        raise BadRequest("'min_score' must be between 0 and 1")
    return float(raw)


def _parse_category(payload):
    """Validate the optional category filter."""
    category = payload.get('category')
    if category is None:
        return None
    if not isinstance(category, str):
        raise BadRequest("'category' must be a string")
    category = category.strip()
    return category or None


# Unexpected failures fall through to the app-level handler in
# register_error_handlers, which logs the traceback and returns a generic
# JSON 500 rather than echoing the exception text back to the client.


def _parse_int_arg(name, default, minimum, maximum=None):
    """Validate an integer query-string argument."""
    raw = request.args.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError) as e:
        raise BadRequest(f"'{name}' must be an integer") from e
    if value < minimum:
        raise BadRequest(f"'{name}' must be at least {minimum}")
    return min(value, maximum) if maximum is not None else value


# Sort keys for GET /api/agents, mapped to (key function, default direction).
AGENT_SORTS = {
    "name": (lambda a: (a["name"] or "").casefold(), "asc"),
    "stars": (lambda a: int(a["metadata"].get("stars") or 0), "desc"),
    "category": (lambda a: ((a["metadata"].get("category") or "").casefold(),
                            (a["name"] or "").casefold()), "asc"),
}


def _parse_sort():
    """Validate the sort key and direction from the query string."""
    key = (request.args.get('sort') or 'name').strip().casefold()
    if key not in AGENT_SORTS:
        raise BadRequest(f"'sort' must be one of: {', '.join(sorted(AGENT_SORTS))}")

    order = (request.args.get('order') or AGENT_SORTS[key][1]).strip().casefold()
    if order not in {"asc", "desc"}:
        raise BadRequest("'order' must be 'asc' or 'desc'")
    return key, order


@api_bp.route('/agents', methods=['GET'])
def get_agents():
    """List agents, one page at a time.

    Returns an envelope rather than a bare array so clients can tell whether
    more pages remain.
    """
    try:
        limit = _parse_int_arg('limit', config.AGENTS_PAGE_SIZE, 1, config.AGENTS_MAX_PAGE_SIZE)
        offset = _parse_int_arg('offset', 0, 0)
        sort_key, order = _parse_sort()
        min_stars = _parse_int_arg('min_stars', None, 0)
        max_stars = _parse_int_arg('max_stars', None, 0)
    except BadRequest as e:
        return jsonify({"error": str(e)}), 400

    if min_stars is not None and max_stars is not None and min_stars > max_stars:
        return jsonify({"error": "'min_stars' cannot exceed 'max_stars'"}), 400

    category = (request.args.get('category') or '').strip() or None
    tech = (request.args.get('tech') or '').strip() or None
    keyword = (request.args.get('q') or '').strip() or None
    # Any of the usual truthy spellings; a query string has no booleans.
    maintained = (request.args.get('maintained') or '').strip().lower() in {
        "1", "true", "yes", "on"}

    agents = get_store().get_all_agents()
    if keyword:
        # Plain substring matching, deliberately not semantic: this answers
        # "find the agent I can already name", which vector search is bad at
        # for short literal strings.
        needle = keyword.casefold()
        agents = [
            a for a in agents
            if needle in (a["name"] or "").casefold()
            or needle in (a["metadata"].get("description") or "").casefold()
        ]
    if category:
        wanted = category.casefold()
        agents = [a for a in agents if (a["metadata"].get("category") or "").casefold() == wanted]
    if maintained:
        agents = [a for a in agents
                  if (a["metadata"].get("status") or "active") == "active"]
    if tech:
        wanted = tech.casefold()
        agents = [
            a for a in agents
            if wanted in {t.strip().casefold() for t in str(a["metadata"].get("stack") or "").split(",")}
        ]

    if min_stars is not None:
        agents = [a for a in agents if int(a["metadata"].get("stars") or 0) >= min_stars]
    if max_stars is not None:
        agents = [a for a in agents if int(a["metadata"].get("stars") or 0) <= max_stars]

    agents.sort(key=AGENT_SORTS[sort_key][0], reverse=(order == "desc"))
    page = agents[offset:offset + limit]

    return jsonify({
        "agents": page,
        "metadata": {
            "total": len(agents),
            "count": len(page),
            "limit": limit,
            "offset": offset,
            "category": category,
            "tech": tech,
            "maintained": maintained,
            "q": keyword,
            "min_stars": min_stars,
            "max_stars": max_stars,
            "sort": sort_key,
            "order": order,
            "has_more": offset + len(page) < len(agents),
        }
    }), 200


@api_bp.route('/agents/<path:name>', methods=['GET'])
def get_agent(name):
    """Fetch a single agent by name."""
    agent = get_store().get_agent(name)
    if agent is None:
        return jsonify({"error": f"No agent named {name!r}"}), 404
    return jsonify(agent), 200


@api_bp.route('/agents/<path:name>/similar', methods=['GET'])
def get_similar_agents(name):
    """Agents similar to the named one, excluding itself."""
    try:
        limit = _parse_int_arg('limit', 3, 1, config.SEARCH_MAX_LIMIT)
    except BadRequest as e:
        return jsonify({"error": str(e)}), 400

    results = get_store().find_similar(name, limit=limit)
    if results is None:
        return jsonify({"error": f"No agent named {name!r}"}), 404

    return jsonify({
        "agents": results,
        "metadata": {"of": name, "count": len(results), "limit": limit},
    }), 200


@api_bp.route('/compare', methods=['GET'])
def compare_agents():
    """Fetch several agents at once for a side-by-side comparison.

    Reports unknown names in `metadata.missing` rather than 404ing the whole
    request, so one typo does not discard the agents that did resolve.
    """
    raw = request.args.get('names') or ''
    names = [n.strip() for n in raw.split(',') if n.strip()]

    if not names:
        return jsonify({"error": "'names' must list at least one agent"}), 400
    if len(names) > config.COMPARE_MAX_AGENTS:
        return jsonify({
            "error": f"'names' accepts at most {config.COMPARE_MAX_AGENTS} agents"
        }), 400

    store = get_store()
    found, missing = [], []
    for name in names:
        agent = store.get_agent(name)
        (found if agent else missing).append(agent or name)

    return jsonify({
        "agents": found,
        "metadata": {
            "requested": len(names),
            "count": len(found),
            "missing": missing,
        },
    }), 200


@api_bp.route('/search', methods=['POST'])
def search_agents():
    payload = request.get_json(silent=True)
    try:
        query = _parse_query(payload)
        limit = _parse_limit(payload)
        category = _parse_category(payload)
        summarize = _parse_summarize(payload)
        min_score = _parse_min_score(payload)
        maintained = _parse_maintained(payload)
    except BadRequest as e:
        return jsonify({"error": str(e)}), 400

    # Searching costs an embedding call; summarizing costs a generation on
    # top, so it gets its own tighter budget.
    key = rate_limit.client_key(request)
    allowed, retry_after = rate_limit.search_limiter.check(key)
    if allowed and summarize:
        allowed, retry_after = rate_limit.summary_limiter.check(key)
    if not allowed:
        logger.warning("Rate limited %s on /api/search", key)
        response = jsonify({
            "error": "Too many requests. Please slow down.",
            "retry_after": round(retry_after, 1),
        })
        response.headers["Retry-After"] = str(max(1, int(retry_after) + 1))
        return response, 429

    start_time = time.time()
    results = get_store().search(query, limit=limit, category=category,
                                 min_score=min_score, maintained=maintained)

    # Vector search always returns *something*, so a nonsense query still gets
    # a full page of cards. Report whether the best match actually cleared the
    # confidence threshold rather than letting the UI imply they are all good.
    confident = bool(results) and results[0]["score"] >= config.SEARCH_MIN_SCORE

    # Retrieval is complete at this point. Generation is a best-effort extra:
    # generation.summarize returns None rather than raising if the chat model
    # is unavailable, so a failure here cannot cost the user their results.
    # Skipped for weak matches: an overview of irrelevant tools reads as
    # confident nonsense.
    summary = generation.summarize(query, results) if summarize and confident else None

    duration = time.time() - start_time
    return jsonify({
        "results": results,
        "summary": summary,
        "metadata": {
            "count": len(results),
            "limit": limit,
            "category": category,
            "maintained": maintained,
            "confident": confident,
            "min_score": min_score,
            "summarized": summary is not None,
            "duration": f"{duration:.2f}s"
        }
    }), 200


@api_bp.route('/categories', methods=['GET'])
def get_categories():
    return _etag_response(get_store().get_categories())


@api_bp.route('/tech', methods=['GET'])
def get_tech_stacks():
    """Technologies across the catalogue, with counts."""
    return _etag_response(get_store().get_tech_stacks())


def _read_changelog():
    """The generated history, or [] when there is none to read.

    Absent is the normal state before changelog.py has ever run, and an empty
    history is a truthful answer to "what changed" — not a 500.
    """
    path = config.DATA_DIR / "changelog.json"
    try:
        with open(path) as f:
            entries = json.load(f)
    except (OSError, json.JSONDecodeError):
        logger.info("No changelog at %s; run changelog.py to build one.", path)
        return []

    return entries if isinstance(entries, list) else []


@api_bp.route('/changelog', methods=['GET'])
def get_changelog():
    """How the catalogue has changed, newest first.

    Generated from git by changelog.py rather than computed here: the web
    process may not have a working tree (a container ships the JSON, not the
    repository), and the history only changes when the catalogue does.
    """
    entries = _read_changelog()

    try:
        limit = _parse_int_arg('limit', 50, 1, 500)
    except BadRequest as e:
        return jsonify({"error": str(e)}), 400

    return _etag_response({
        "entries": entries[:limit],
        "metadata": {"count": min(len(entries), limit), "total": len(entries)},
    })


def _feed_summary(entry):
    """One entry as a sentence, for a reader that shows no markup."""
    parts = []
    if entry.get("added"):
        parts.append(f"Added {', '.join(entry['added'])}")
    if entry.get("removed"):
        parts.append(f"Removed {', '.join(entry['removed'])}")
    if entry.get("edited"):
        names = [e.get("name", "?") for e in entry["edited"]]
        shown = ", ".join(names[:5]) + (f" and {len(names) - 5} more" if len(names) > 5 else "")
        parts.append(f"Edited {shown}")
    parts.append(f"{entry.get('total', 0)} agents in the catalogue")
    return ". ".join(parts) + "."


@api_bp.route('/changelog.atom', methods=['GET'])
def get_changelog_feed():
    """The same history as an Atom feed, for anyone following along.

    Atom rather than RSS: it requires a stable id and a real timestamp per
    entry, both of which a git commit already has, and readers treat those
    as the identity of an item rather than guessing from the title.
    """
    entries = _read_changelog()[:50]
    origin = request.url_root.rstrip("/")

    feed = ET.Element("feed", {"xmlns": "http://www.w3.org/2005/Atom"})
    ET.SubElement(feed, "title").text = "AI Agent Discovery — catalogue changes"
    ET.SubElement(feed, "id").text = f"{origin}/api/changelog.atom"
    ET.SubElement(feed, "link", {"href": f"{origin}/changes"})
    ET.SubElement(feed, "link", {"rel": "self", "href": f"{origin}/api/changelog.atom"})
    # An empty feed still needs one: readers treat a missing updated as
    # malformed rather than as "nothing yet".
    ET.SubElement(feed, "updated").text = (
        entries[0].get("at") if entries else datetime.now(timezone.utc).isoformat())

    for entry in entries:
        item = ET.SubElement(feed, "entry")
        ET.SubElement(item, "title").text = entry.get("subject") or "Catalogue change"
        # The commit, not the position: an id that shifts as history grows
        # makes every reader re-announce every entry.
        ET.SubElement(item, "id").text = f"{origin}/changes#{entry.get('commit', '')}"
        ET.SubElement(item, "link", {"href": f"{origin}/changes"})
        ET.SubElement(item, "updated").text = entry.get("at") or ""
        ET.SubElement(item, "summary").text = _feed_summary(entry)

    xml = ET.tostring(feed, encoding="utf-8", xml_declaration=True)
    response = make_response(xml)
    response.headers["Content-Type"] = "application/atom+xml; charset=utf-8"
    return response


@api_bp.route('/stats', methods=['GET'])
def get_stats():
    return _etag_response(get_store().get_stats())


# Described by hand because the meaning of these fields is not derivable from
# the route: `score` is a cosine similarity except when `match` is "name", in
# which case it is 1.0 because the query was the agent's name.
_SCHEMAS = {
    "SearchResult": {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "description": {"type": "string", "description": "The agent's own description."},
            "matched_text": {"type": "string", "description": "The composite text that was embedded."},
            "distance": {"type": "number", "description": "L2 distance from the query vector."},
            "score": {
                "type": "number",
                "description": (
                    "Cosine similarity in 0..1, recovered from the distance. "
                    "Exactly 1.0 when match is 'name' — that is an exact match "
                    "on the name, not a similarity measurement."
                ),
            },
            "match": {
                "type": "string",
                "enum": ["semantic", "name"],
                "description": (
                    "'semantic' for a similarity hit; 'name' when the query was "
                    "exactly this agent's name, in which case it is ranked first."
                ),
            },
            "metadata": {"type": "object"},
        },
    },
    "SearchResponse": {
        "type": "object",
        "properties": {
            "results": {"type": "array", "items": {"$ref": "#/components/schemas/SearchResult"}},
            "summary": {
                "type": ["string", "null"],
                "description": "LLM overview; null unless requested and generation succeeded.",
            },
            "metadata": {
                "type": "object",
                "properties": {
                    "count": {"type": "integer"},
                    "limit": {"type": "integer"},
                    "category": {"type": ["string", "null"]},
                    "min_score": {"type": ["number", "null"]},
                    "confident": {
                        "type": "boolean",
                        "description": "False when the best result scored below SEARCH_MIN_SCORE.",
                    },
                    "summarized": {"type": "boolean"},
                    "duration": {"type": "string"},
                },
            },
        },
    },
}


@api_bp.route('/openapi.json', methods=['GET'])
def openapi():
    """A machine-readable description of this API.

    Generated from the live URL map rather than hand-written, so it cannot
    drift from the routes that actually exist. Descriptions come from each
    handler's docstring.
    """
    from flask import current_app

    paths = {}
    for rule in current_app.url_map.iter_rules():
        if not rule.rule.startswith(api_bp.url_prefix + "/"):
            continue

        handler = current_app.view_functions.get(rule.endpoint)
        summary = ((handler.__doc__ or "").strip().split("\n")[0]) if handler else ""

        # Flask writes <converter:name>; OpenAPI wants {name}.
        path = re.sub(r"<(?:[^:<>]+:)?([^<>]+)>", r"{\1}", rule.rule)
        entry = paths.setdefault(path, {})

        for method in sorted(rule.methods - {"HEAD", "OPTIONS"}):
            operation = {"summary": summary, "responses": {"200": {"description": "Success"}}}

            parameters = [
                {"name": name, "in": "path", "required": True, "schema": {"type": "string"}}
                for name in rule.arguments
            ]
            if parameters:
                operation["parameters"] = parameters
            entry[method.lower()] = operation

    # Only the search response is described in full. The rest are generated
    # from the URL map with a generic 200, which is honest about what is
    # known; hand-writing schemas for every route would drift the moment a
    # handler changed. Search is the exception because callers have to
    # interpret `score` and `match` correctly to use it at all.
    if "/api/search" in paths and "post" in paths["/api/search"]:
        paths["/api/search"]["post"]["responses"]["200"] = {
            "description": "Ranked results",
            "content": {"application/json": {"schema": {"$ref": "#/components/schemas/SearchResponse"}}},
        }

    return jsonify({
        "openapi": "3.0.3",
        "info": {
            "title": "AI Agent Discovery",
            "version": "1.0.0",
            "description": "Semantic search over a curated catalogue of AI agents and developer tools.",
        },
        "paths": paths,
        "components": {"schemas": _SCHEMAS},
    }), 200


@api_bp.route('/submissions', methods=['POST'])
def submit_agent():
    """Propose an agent for the catalogue.

    Public, unlike /api/admin: a submission is only a proposal. It is
    validated with the same rules as a direct edit, then queued — nothing
    reaches the catalogue until a maintainer approves it, so the write path
    stays as restricted as it was.
    """
    if not config.ENABLE_SUBMISSIONS:
        return jsonify({"error": "Submissions are closed."}), 403

    import submissions
    from admin import AdminError

    allowed, retry_after = rate_limit.submission_limiter.check(rate_limit.client_key(request))
    if not allowed:
        response = jsonify({"error": "Too many submissions. Try again shortly."})
        response.headers["Retry-After"] = str(retry_after)
        return response, 429

    try:
        entry = submissions.submit(request.get_json(silent=True))
    except AdminError as e:
        return jsonify({"error": str(e)}), e.status

    return jsonify({
        "id": entry["id"],
        "status": entry["status"],
        "agent": entry["agent"],
        "note": "Queued for review. It will appear once a maintainer approves it.",
    }), 202


@api_bp.route('/health', methods=['GET'])
def health():
    """Readiness probe: reports whether the index is actually usable.

    Returns 503 when the store cannot be built or holds no vectors, so a
    "running but unseeded" app is distinguishable from a healthy one.
    """
    payload = {
        "status": "ok",
        "model": config.MODEL_NAME,
        "embedding_model": config.EMBEDDING_MODEL,
        "ollama_url": config.OLLAMA_BASE_URL,
        "index_path": str(config.FAISS_DIR),
        "index_built_at": None,
        "indexed_agents": 0,
    }

    try:
        stats = get_store().get_stats()
        payload["indexed_agents"] = stats.get("count", 0)
        payload["index_built_at"] = stats.get("built_at")
        payload["catalogue_stale"] = stats.get("catalogue_stale")
    except Exception as e:
        logger.exception("Health check could not reach the vector store")
        payload.update(status="error", detail=str(e))
        return jsonify(payload), 503

    # A drifted catalogue still serves results, just outdated ones, so this is
    # a warning on an otherwise healthy response rather than a 503.
    if payload.get("catalogue_stale"):
        payload["detail"] = (
            "data/agents.json has changed since the index was built. "
            "Run seed.py to pick up the edits."
        )

    if payload["indexed_agents"] == 0:
        detail = "No agents indexed. Run seed.py to populate the vector store."
        stale = getattr(get_store(), "stale_model", None)
        if stale:
            detail = (
                f"Index was built with embedding model {stale!r} but {config.EMBEDDING_MODEL!r} "
                "is configured. Re-run seed.py to rebuild it."
            )
        payload.update(status="degraded", detail=detail)
        return jsonify(payload), 503

    return jsonify(payload), 200
