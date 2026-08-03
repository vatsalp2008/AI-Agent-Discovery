"""Shared logging setup.

Entry points (the Flask app, the seed script, the CLI) call ``configure()``
once; library modules just use ``logging.getLogger(__name__)``.
"""

import logging

import config

_configured = False


def configure(level=None):
    """Install a console handler on the root logger. Idempotent."""
    global _configured
    if _configured:
        return
    logging.basicConfig(
        level=getattr(logging, level or config.LOG_LEVEL, logging.INFO),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    _configured = True
