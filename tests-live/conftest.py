"""Fixtures for the live suite.

Deliberately does NOT stub langchain or Ollama — that is the whole point of
these tests. It lives in its own directory so the stubs installed by
tests/conftest.py cannot leak in.
"""

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND = REPO_ROOT / "ai-agent-discovery" / "backend"
sys.path.insert(0, str(BACKEND))


# --- Guard against a silently-skipped live suite -------------------------
#
# These tests skip themselves when Ollama is unreachable or a model is not
# pulled, which is right for a laptop but wrong for CI: a broken setup would
# report success having verified nothing. Setting LIVE_TESTS_REQUIRED=1 turns
# any skip into a failure.
#
# This lives here rather than as a `grep skipped` on pytest's console output,
# which matched human-readable text that pytest is free to reword.

# Reports carry no back-reference to the session, so collect here.
_skipped: list[tuple[str, str]] = []


def pytest_runtest_logreport(report):
    if report.skipped and report.when == "setup":
        reason = ""
        if isinstance(report.longrepr, tuple) and len(report.longrepr) == 3:
            reason = report.longrepr[2]
        _skipped.append((report.nodeid, reason))


def pytest_sessionfinish(session, exitstatus):
    if os.getenv("LIVE_TESTS_REQUIRED", "").strip() not in {"1", "true", "yes"}:
        return

    skipped = list(_skipped)
    if not skipped:
        return

    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    if reporter:
        reporter.write_sep("=", "live tests were required but skipped", red=True)
        for nodeid, reason in skipped:
            reporter.write_line(f"  {nodeid}: {reason}")
        reporter.write_line(
            "LIVE_TESTS_REQUIRED=1 is set, so a skipped live suite is a failure. "
            "Check that Ollama is reachable and both models are pulled."
        )
    session.exitstatus = 1
