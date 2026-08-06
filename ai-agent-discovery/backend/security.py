"""Baseline security response headers.

Agent records are hand-edited JSON rendered into the page, so the frontend
already builds every card with DOM APIs rather than innerHTML. These headers
are the belt to that braces: if an escaping bug ever slips through, a content
security policy limits what an injected script could do.

The policy has to allow the two CDNs the pages actually use (Google Fonts and
Ionicons). It deliberately does not allow 'unsafe-inline' for scripts, which
is only possible because no template contains an inline <script>.
"""

import config

CSP_DIRECTIVES = {
    "default-src": ["'self'"],
    "script-src": ["'self'", "https://unpkg.com"],
    # Google Fonts serves its stylesheet from fonts.googleapis.com.
    # 'unsafe-inline' is needed only by the Ionicons web component, which
    # injects its own <style>; no template contains an inline style. Injected
    # CSS is far less dangerous than injected script, which stays disallowed.
    "style-src": ["'self'", "https://fonts.googleapis.com", "'unsafe-inline'"],
    "font-src": ["'self'", "https://fonts.gstatic.com"],
    "img-src": ["'self'", "data:"],
    "connect-src": ["'self'"],
    "frame-ancestors": ["'none'"],
    "base-uri": ["'self'"],
    "form-action": ["'self'"],
}


def build_csp() -> str:
    return "; ".join(f"{name} {' '.join(values)}" for name, values in CSP_DIRECTIVES.items())


HEADERS = {
    "Content-Security-Policy": build_csp(),
    # Stops browsers guessing a different content type than we declared.
    "X-Content-Type-Options": "nosniff",
    # Do not leak the query string of a search to third-party CDNs.
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "X-Frame-Options": "DENY",
    # This app needs none of these.
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
}


def register(app):
    """Attach the headers to every response."""

    @app.after_request
    def _apply(response):
        for name, value in HEADERS.items():
            response.headers.setdefault(name, value)
        return response

    if config.DEBUG:
        # The Werkzeug debugger needs inline scripts to function; warn rather
        # than silently shipping a policy that blocks it.
        app.logger.warning("FLASK_DEBUG is on; the CSP will block the interactive debugger.")

    return app
