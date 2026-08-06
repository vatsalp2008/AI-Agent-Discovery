"""A small in-process rate limiter for the search endpoint.

Searching costs an embedding call, and a search with `summarize` costs a text
generation on top — both hit Ollama, both are far more expensive than an
ordinary request. The app binds to loopback by default, but the container
image binds 0.0.0.0, and a runaway client loop can saturate the machine either
way. A generous cap keeps normal use unaffected while stopping a stampede.

Deliberately in-memory and per-process: this is a single-process local app, and
pulling in Redis to protect it would be worse than the problem. Counters reset
on restart, which is fine for that purpose.
"""

import logging
import threading
import time
from collections import defaultdict, deque

import config

logger = logging.getLogger(__name__)


class SlidingWindowLimiter:
    """Allows `limit` events per `window` seconds, per key.

    A sliding window rather than a fixed one so a client cannot fire 2x the
    limit by straddling a window boundary.
    """

    def __init__(self, limit: int, window: float = 60.0):
        self.limit = limit
        self.window = window
        self._hits = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str):
        """Record an attempt. Returns (allowed, retry_after_seconds)."""
        if self.limit <= 0:  # disabled
            return True, 0.0

        now = time.monotonic()
        cutoff = now - self.window

        with self._lock:
            # Drop keys whose hits have all aged out, so the table does not
            # grow one permanent entry per client address ever seen.
            for other, hits in list(self._hits.items()):
                if other != key and (not hits or hits[-1] <= cutoff):
                    del self._hits[other]

            hits = self._hits[key]
            while hits and hits[0] <= cutoff:
                hits.popleft()

            if len(hits) >= self.limit:
                # The oldest hit falls out of the window at hits[0] + window.
                return False, max(0.0, hits[0] + self.window - now)

            hits.append(now)
            return True, 0.0

    def reset(self):
        with self._lock:
            self._hits.clear()


# One limiter for ordinary searches, a tighter one for generation.
search_limiter = SlidingWindowLimiter(config.RATE_LIMIT_SEARCHES)
summary_limiter = SlidingWindowLimiter(config.RATE_LIMIT_SUMMARIES)


def client_key(request) -> str:
    """Identify the caller. Remote address is enough for a local app."""
    return request.remote_addr or "unknown"


def reset_all():
    """Clear all counters. Used by tests."""
    search_limiter.reset()
    summary_limiter.reset()
