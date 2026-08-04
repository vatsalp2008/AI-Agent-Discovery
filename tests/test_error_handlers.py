"""Failures under /api must be JSON, not Flask's HTML error page."""

import api


def test_unknown_api_path_returns_json_404(client):
    response = client.get("/api/does-not-exist")
    assert response.status_code == 404
    assert response.is_json
    assert response.get_json()["error"] == "Not found"


def test_wrong_method_returns_json_405(client):
    response = client.get("/api/search")  # search is POST-only
    assert response.status_code == 405
    assert response.is_json
    assert "not allowed" in response.get_json()["error"]


def test_unexpected_error_returns_json_500_without_leaking_details(client):
    class Exploding:
        def get_all_agents(self):
            raise RuntimeError("secret internal detail")

    api.set_store(Exploding())
    response = client.get("/api/agents")
    assert response.status_code == 500
    assert response.is_json
    assert response.get_json() == {"error": "Internal server error"}
    assert "secret internal detail" not in response.get_data(as_text=True)


def test_non_api_paths_keep_html_errors(client):
    """The browser UI should still get Flask's normal error pages."""
    response = client.get("/definitely-not-a-page")
    assert response.status_code == 404
    assert not response.is_json


def test_successful_requests_are_unaffected(client):
    assert client.get("/api/stats").status_code == 200
