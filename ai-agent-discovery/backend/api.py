import logging
import time

from flask import Blueprint, request, jsonify

import config
from vectorstore import VectorStore

logger = logging.getLogger(__name__)

api_bp = Blueprint('api', __name__, url_prefix='/api')
vs = VectorStore()


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


@api_bp.route('/agents', methods=['GET'])
def get_agents():
    try:
        agents = vs.get_all_agents()
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
    except BadRequest as e:
        return jsonify({"error": str(e)}), 400

    start_time = time.time()
    try:
        results = vs.search(query, limit=limit)
    except Exception as e:
        logger.exception("Search failed for query %r", query)
        return jsonify({"error": str(e)}), 500

    duration = time.time() - start_time
    return jsonify({
        "results": results,
        "metadata": {
            "count": len(results),
            "limit": limit,
            "duration": f"{duration:.2f}s"
        }
    }), 200


@api_bp.route('/stats', methods=['GET'])
def get_stats():
    try:
        stats = vs.get_stats()
        return jsonify(stats), 200
    except Exception as e:
        logger.exception("Failed to compute stats")
        return jsonify({"error": str(e)}), 500
