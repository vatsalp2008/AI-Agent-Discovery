from flask import Blueprint, request, jsonify
from vectorstore import VectorStore
import time

api_bp = Blueprint('api', __name__, url_prefix='/api')
vs = VectorStore()

@api_bp.route('/agents', methods=['GET'])
def get_agents():
    try:
        agents = vs.get_all_agents()
        return jsonify(agents), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api_bp.route('/search', methods=['POST'])
def search_agents():
    data = request.json
    query = data.get('query')
    if not query:
        return jsonify({"error": "No query provided"}), 400
    
    start_time = time.time()
    try:
        results = vs.search(query)
        duration = time.time() - start_time
        return jsonify({
            "results": results,
            "metadata": {
                "count": len(results),
                "duration": f"{duration:.2f}s"
            }
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api_bp.route('/stats', methods=['GET'])
def get_stats():
    try:
        stats = vs.get_stats()
        return jsonify(stats), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
