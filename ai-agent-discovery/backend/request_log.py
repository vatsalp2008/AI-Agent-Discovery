"""Per-request timing.

Search latency is dominated by calls out to Ollama, so knowing how long a
request took — and which ones are slow — is the first thing you want when the
app feels sluggish. Requests slower than SLOW_REQUEST_MS are logged at
WARNING so they stand out without turning on debug logging.
"""

import logging
import time

from flask import g, request

import config

logger = logging.getLogger(__name__)


def register(app):
    """Attach timing hooks to a Flask app."""

    @app.before_request
    def _start_timer():
        g._request_start = time.perf_counter()

    @app.after_request
    def _log_request(response):
        start = g.pop('_request_start', None)
        if start is None:
            return response

        elapsed_ms = (time.perf_counter() - start) * 1000
        response.headers['X-Response-Time'] = f"{elapsed_ms:.1f}ms"

        # Static assets are noise; they never touch Ollama or the index.
        if request.endpoint == 'static':
            return response

        level = logging.WARNING if elapsed_ms >= config.SLOW_REQUEST_MS else logging.INFO
        logger.log(
            level,
            "%s %s -> %s in %.1fms%s",
            request.method,
            request.full_path.rstrip('?'),
            response.status_code,
            elapsed_ms,
            "  (slow)" if level == logging.WARNING else "",
        )
        return response

    return app
