"""Check that everything this project needs is actually in place.

    python ai-agent-discovery/doctor.py
    python ai-agent-discovery/doctor.py --json

Setup problems otherwise surface as confusing symptoms: an unreachable Ollama
looks like "no results", a missing model looks like a hang, and an index built
by a different embedding model looks like nonsense rankings. Each check below
says what is wrong and what to do about it.

Exit code is 0 when everything required passes, 1 otherwise, so it can gate a
script.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), 'backend')))

import config  # noqa: E402
from logging_setup import configure  # noqa: E402

OK, WARN, FAIL = "ok", "warning", "failed"


def _result(name, status, detail, fix=None, required=True):
    return {"check": name, "status": status, "detail": detail, "fix": fix, "required": required}


def check_ollama():
    """Is the Ollama server reachable?"""
    url = f"{config.OLLAMA_BASE_URL.rstrip('/')}/api/tags"
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            json.load(response)
        return _result("ollama", OK, f"reachable at {config.OLLAMA_BASE_URL}")
    except urllib.error.URLError as e:
        return _result("ollama", FAIL, f"cannot reach {config.OLLAMA_BASE_URL}: {e.reason}",
                       fix="Start it with `ollama serve`, or set OLLAMA_BASE_URL.")
    except Exception as e:
        return _result("ollama", FAIL, f"unexpected response from {config.OLLAMA_BASE_URL}: {e}",
                       fix="Check that OLLAMA_BASE_URL points at an Ollama server.")


def _installed_models():
    url = f"{config.OLLAMA_BASE_URL.rstrip('/')}/api/tags"
    with urllib.request.urlopen(url, timeout=5) as response:
        payload = json.load(response)
    return [m.get("name", "") for m in payload.get("models", [])]


def _model_present(installed, wanted):
    """Is `wanted` among the installed models?

    Ollama reports "name:tag". A bare name should match whatever tag is
    installed, since `ollama pull nomic-embed-text` gives you `:latest`. But
    an explicit tag must match exactly — otherwise asking for
    "nomic-embed-text:v1.5" reports OK when only ":latest" is present, which
    is precisely the mismatch this check exists to catch.
    """
    if ":" in wanted:
        return wanted in installed
    return any(name == wanted or name.split(":")[0] == wanted for name in installed)


def check_embedding_model():
    try:
        installed = _installed_models()
    except Exception as e:
        return _result("embedding model", FAIL, f"could not list models: {e}",
                       fix="Fix the Ollama connection first.")

    if _model_present(installed, config.EMBEDDING_MODEL):
        return _result("embedding model", OK, f"{config.EMBEDDING_MODEL} is installed")
    return _result("embedding model", FAIL, f"{config.EMBEDDING_MODEL} is not installed",
                   fix=f"ollama pull {config.EMBEDDING_MODEL}")


def check_chat_model():
    """Optional: only the AI overview needs it."""
    try:
        installed = _installed_models()
    except Exception as e:
        return _result("chat model", WARN, f"could not list models: {e}", required=False)

    if _model_present(installed, config.MODEL_NAME):
        return _result("chat model", OK, f"{config.MODEL_NAME} is installed", required=False)
    return _result("chat model", WARN,
                   f"{config.MODEL_NAME} is not installed; AI overviews will be skipped",
                   fix=f"ollama pull {config.MODEL_NAME}", required=False)


def check_catalogue():
    if not os.path.exists(config.AGENTS_JSON):
        return _result("catalogue", WARN,
                       f"{config.AGENTS_JSON} does not exist; the built-in samples will be used",
                       fix="Run seed.py to create it.", required=False)
    try:
        with open(config.AGENTS_JSON) as f:
            records = json.load(f)
    except json.JSONDecodeError as e:
        return _result("catalogue", FAIL, f"{config.AGENTS_JSON} is not valid JSON: {e}",
                       fix="Fix the syntax, or restore it from git.")
    except OSError as e:
        return _result("catalogue", FAIL, f"cannot read {config.AGENTS_JSON}: {e}")

    if not isinstance(records, list):
        return _result("catalogue", FAIL, "the catalogue must be a JSON array")
    return _result("catalogue", OK, f"{len(records)} agents in {config.AGENTS_JSON}")


def check_index():
    index_file = os.path.join(str(config.FAISS_DIR), "index.faiss")
    if not os.path.exists(index_file):
        return _result("index", FAIL, f"no index at {config.FAISS_DIR}",
                       fix="Run seed.py to build it.")

    meta_path = os.path.join(str(config.FAISS_DIR), "index_meta.json")
    try:
        with open(meta_path) as f:
            meta = json.load(f)
    except (OSError, json.JSONDecodeError):
        return _result("index", WARN, "index present, but it has no metadata sidecar",
                       fix="Re-run seed.py to record which model built it.", required=False)

    built_by = meta.get("embedding_model")
    if built_by and built_by != config.EMBEDDING_MODEL:
        return _result("index", FAIL,
                       f"built with {built_by!r}, but {config.EMBEDDING_MODEL!r} is configured",
                       fix="Run seed.py to rebuild it; vectors from one model are unusable by another.")
    return _result("index", OK,
                   f"{meta.get('agent_count', '?')} agents, built {meta.get('built_at', 'at an unknown time')}")


def check_catalogue_freshness():
    """Has the catalogue been edited since the index was built?"""
    meta_path = os.path.join(str(config.FAISS_DIR), "index_meta.json")
    if not (os.path.exists(meta_path) and os.path.exists(config.AGENTS_JSON)):
        return None
    try:
        with open(meta_path) as f:
            built = json.load(f).get("built_at")
        if not built:
            return None
        from datetime import datetime

        built_ts = datetime.fromisoformat(built).timestamp()
    except (OSError, json.JSONDecodeError, ValueError):
        return None

    # Same grace period as VectorStore.catalogue_is_stale, taken from there so
    # doctor and /api/admin/status cannot disagree if it is ever tuned.
    from vectorstore import VectorStore

    if os.path.getmtime(config.AGENTS_JSON) > built_ts + VectorStore.FRESHNESS_GRACE_SECONDS:
        return _result("freshness", WARN, "the catalogue has changed since the index was built",
                       fix="Run seed.py to pick up the edits.", required=False)
    return _result("freshness", OK, "the index matches the catalogue", required=False)


def check_admin():
    """Editing is a write surface with no authentication."""
    if not config.ENABLE_ADMIN:
        return _result("catalogue editing", OK, "disabled (the default)", required=False)

    host = config.HOST
    if host in {"127.0.0.1", "localhost", "::1"}:
        return _result("catalogue editing", OK, f"enabled, bound to {host}", required=False)
    return _result("catalogue editing", WARN,
                   f"enabled with HOST={host}, which is reachable from the network",
                   fix="Set HOST=127.0.0.1, or turn ENABLE_ADMIN off.", required=False)


CHECKS = (check_ollama, check_embedding_model, check_chat_model,
          check_catalogue, check_index, check_catalogue_freshness, check_admin)


def run_checks():
    results = []
    for check in CHECKS:
        result = check()
        if result is not None:
            results.append(result)
    return results


SYMBOLS = {OK: "ok  ", WARN: "warn", FAIL: "FAIL"}


def render(results):
    lines = []
    for r in results:
        lines.append(f"  [{SYMBOLS[r['status']]}] {r['check']:<18} {r['detail']}")
        if r["fix"] and r["status"] != OK:
            lines.append(f"         -> {r['fix']}")

    failed = [r for r in results if r["status"] == FAIL]
    warned = [r for r in results if r["status"] == WARN]
    lines.append("")
    if failed:
        lines.append(f"{len(failed)} check(s) failed. Search will not work until they are fixed.")
    elif warned:
        lines.append(f"Everything required is in place, with {len(warned)} warning(s).")
    else:
        lines.append("Everything looks good.")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="doctor.py", description=__doc__.split("\n")[0])
    parser.add_argument("--json", action="store_true", dest="as_json",
                        help="emit JSON instead of a report")
    args = parser.parse_args(argv)

    configure("ERROR")
    results = run_checks()
    print(json.dumps(results, indent=2) if args.as_json else render(results))
    return 1 if any(r["status"] == FAIL for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
