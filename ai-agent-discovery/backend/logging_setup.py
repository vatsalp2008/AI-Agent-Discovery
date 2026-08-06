"""Shared logging setup.

Entry points (the Flask app, the seed script, the CLI) call ``configure()``
once; library modules just use ``logging.getLogger(__name__)``.

Two formats are available. The default is human-readable text for local use.
Setting ``LOG_FORMAT=json`` emits one JSON object per line instead, which is
what a log collector needs: the request fields that ``request_log`` attaches
become real keys rather than text a downstream regex has to pick apart.
"""

import datetime as _datetime
import json
import logging

import config

_configured = False

# Attributes present on every LogRecord. Anything else was attached by a
# caller via `extra=` and belongs in the JSON output.
_STANDARD_ATTRS = frozenset(vars(logging.LogRecord("", 0, "", 0, "", (), None)))


class JsonFormatter(logging.Formatter):
    """Render each record as a single-line JSON object."""

    def format(self, record):
        payload = {
            "timestamp": _datetime.datetime.fromtimestamp(
                record.created, tz=_datetime.timezone.utc
            ).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        # Merge anything passed as logger.info(..., extra={...}).
        for key, value in vars(record).items():
            if key not in _STANDARD_ATTRS and key != "message":
                payload[key] = value if _is_jsonable(value) else repr(value)

        return json.dumps(payload, default=str)


def _is_jsonable(value):
    return isinstance(value, (str, int, float, bool, type(None), list, dict))


def _build_handler():
    handler = logging.StreamHandler()
    if config.LOG_FORMAT == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            fmt="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        ))
    return handler


def configure(level=None):
    """Install a console handler on the root logger. Idempotent."""
    global _configured
    if _configured:
        return

    root = logging.getLogger()
    root.setLevel(getattr(logging, level or config.LOG_LEVEL, logging.INFO))
    root.addHandler(_build_handler())
    _configured = True


def reset():
    """Undo configure(). Used by tests."""
    global _configured
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
    _configured = False
