import logging
import time

from flask import Blueprint, jsonify, request
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
    except BadRequest as e:
        return jsonify({"error": str(e)}), 400

    category = (request.args.get('category') or '').strip() or None
    tech = (request.args.get('tech') or '').strip() or None
    keyword = (request.args.get('q') or '').strip() or None

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
    if tech:
        wanted = tech.casefold()
        agents = [
            a for a in agents
            if wanted in {t.strip().casefold() for t in str(a["metadata"].get("stack") or "").split(",")}
        ]

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
            "q": keyword,
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
    results = get_store().search(query, limit=limit, category=category, min_score=min_score)

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
            "confident": confident,
            "min_score": min_score,
            "summarized": summary is not None,
            "duration": f"{duration:.2f}s"
        }
    }), 200


@api_bp.route('/categories', methods=['GET'])
def get_categories():
    return jsonify(get_store().get_categories()), 200


@api_bp.route('/tech', methods=['GET'])
def get_tech_stacks():
    """Technologies across the catalogue, with counts."""
    return jsonify(get_store().get_tech_stacks()), 200


@api_bp.route('/stats', methods=['GET'])
def get_stats():
    return jsonify(get_store().get_stats()), 200


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
