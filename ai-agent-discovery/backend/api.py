import logging
import time

from flask import Blueprint, request, jsonify

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
    except (TypeError, ValueError):
        raise BadRequest("'limit' must be an integer")
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


@api_bp.route('/agents', methods=['GET'])
def get_agents():
    try:
        agents = get_store().get_all_agents()
        return jsonify(agents), 200
    except Exception as e:
        logger.exception("Failed to list agents")
        return jsonify({"error": str(e)}), 500


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
    try:
        results = get_store().search(query, limit=limit, category=category)
    except Exception as e:
        logger.exception("Search failed for query %r", query)
        return jsonify({"error": str(e)}), 500

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
    try:
        return jsonify(get_store().get_categories()), 200
    except Exception as e:
        logger.exception("Failed to list categories")
        return jsonify({"error": str(e)}), 500


@api_bp.route('/stats', methods=['GET'])
def get_stats():
    try:
        stats = get_store().get_stats()
        return jsonify(stats), 200
    except Exception as e:
        logger.exception("Failed to compute stats")
        return jsonify({"error": str(e)}), 500


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
        payload.update(status="degraded", detail="No agents indexed. Run seed.py to populate the vector store.")
        return jsonify(payload), 503

    return jsonify(payload), 200
