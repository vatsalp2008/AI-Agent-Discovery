"""Fixtures for the live suite.

Deliberately does NOT stub langchain or Ollama — that is the whole point of
these tests. It lives in its own directory so the stubs installed by
tests/conftest.py cannot leak in.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND = REPO_ROOT / "ai-agent-discovery" / "backend"
sys.path.insert(0, str(BACKEND))
