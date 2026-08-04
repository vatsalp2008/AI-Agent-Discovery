import logging
import time

from flask import Blueprint, jsonify, request
from werkzeug.exceptions import HTTPException

import config
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


@api_bp.route('/agents', methods=['GET'])
def get_agents():
    """List agents, one page at a time.

    Returns an envelope rather than a bare array so clients can tell whether
    more pages remain.
    """
    try:
        limit = _parse_int_arg('limit', config.AGENTS_PAGE_SIZE, 1, config.AGENTS_MAX_PAGE_SIZE)
        offset = _parse_int_arg('offset', 0, 0)
    except BadRequest as e:
        return jsonify({"error": str(e)}), 400

    agents = get_store().get_all_agents()
    page = agents[offset:offset + limit]

    return jsonify({
        "agents": page,
        "metadata": {
            "total": len(agents),
            "count": len(page),
            "limit": limit,
            "offset": offset,
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


@api_bp.route('/search', methods=['POST'])
def search_agents():
    payload = request.get_json(silent=True)
    try:
        query = _parse_query(payload)
        limit = _parse_limit(payload)
        category = _parse_category(payload)
    except BadRequest as e:
        return jsonify({"error": str(e)}), 400

    start_time = time.time()
    results = get_store().search(query, limit=limit, category=category)
    duration = time.time() - start_time
    return jsonify({
        "results": results,
        "metadata": {
            "count": len(results),
            "limit": limit,
            "category": category,
            "duration": f"{duration:.2f}s"
        }
    }), 200


@api_bp.route('/categories', methods=['GET'])
def get_categories():
    return jsonify(get_store().get_categories()), 200


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
        "indexed_agents": 0,
    }

    try:
        payload["indexed_agents"] = get_store().get_stats().get("count", 0)
    except Exception as e:
        logger.exception("Health check could not reach the vector store")
        payload.update(status="error", detail=str(e))
        return jsonify(payload), 503

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
