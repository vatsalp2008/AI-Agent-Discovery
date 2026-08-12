"""A review queue for proposed agents.

`admin.py` writes straight to the catalogue and is therefore disabled by
default — it has no authentication, so anyone who could reach it could rewrite
the catalogue. That makes it a maintainer's tool, not a way for someone to
suggest an agent.

This is the other half: submissions are validated exactly as an edit would be,
but land in a pending queue instead of the catalogue. Nothing reaches
`agents.json` until a maintainer approves it through the admin API, so the
write path stays as restricted as before.

The queue is a JSONL file. It is append-mostly, survives a crash mid-write,
and can be read with `tail` — the same reasoning as the audit log.
"""

import json
import logging
import os
import threading
import uuid
from datetime import datetime, timezone

import config
from admin import EDITABLE_FIELDS, AdminError, load_catalogue, validate

logger = logging.getLogger(__name__)

PENDING, APPROVED, REJECTED = "pending", "approved", "rejected"

# Rewriting the queue to change one status is a read-modify-write, so it needs
# the same serialisation as the catalogue itself.
_queue_lock = threading.Lock()


def _path():
    return str(config.SUBMISSIONS_PATH or "")


def read_all(status=None):
    """Every submission, newest first, optionally filtered by status."""
    path = _path()
    if not path or not os.path.exists(path):
        return []

    try:
        with open(path) as f:
            lines = f.readlines()
    except OSError as e:
        logger.warning("Could not read the submission queue: %s", e)
        return []

    entries = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue  # a truncated line must not hide the rest
        if isinstance(entry, dict):
            entries.append(entry)

    entries.reverse()
    if status:
        entries = [e for e in entries if e.get("status") == status]
    return entries


def _write_all(entries):
    """Rewrite the queue atomically, oldest first."""
    path = _path()
    if not path:
        return
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        tmp = f"{path}.tmp"
        with open(tmp, "w") as f:
            for entry in reversed(entries):
                f.write(json.dumps(entry) + "\n")
        os.replace(tmp, path)
    except OSError as e:
        raise AdminError(f"Could not write the submission queue: {e}", status=500) from e


def submit(record):
    """Validate a proposal and add it to the queue.

    Validated with the same rules as a direct edit, so a submission that would
    never be accepted is rejected now rather than wasting a reviewer's time.
    The uniqueness check runs against the catalogue *and* the pending queue —
    two people proposing the same agent should not both sit there.
    """
    path = _path()
    if not path:
        raise AdminError("Submissions are disabled.", status=403)

    with _queue_lock:
        existing = load_catalogue()
        pending = read_all(status=PENDING)
        # validate() only understands catalogue records, so present the
        # pending proposals in the same shape.
        against = existing + [e["agent"] for e in pending if isinstance(e.get("agent"), dict)]

        cleaned = validate(record, against)

        entry = {
            "id": uuid.uuid4().hex[:12],
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "status": PENDING,
            "agent": cleaned,
        }
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except OSError as e:
            raise AdminError(f"Could not record the submission: {e}", status=500) from e

    logger.info("Agent %r submitted for review (%s)", cleaned["name"], entry["id"])
    return entry


def _find(entries, submission_id):
    for entry in entries:
        if entry.get("id") == submission_id:
            return entry
    return None


def decide(submission_id, status, note=None):
    """Mark a submission approved or rejected.

    Approval records the decision; it does not write to the catalogue. The
    caller does that, so the existing validation, locking and audit trail on
    the write path are not bypassed.
    """
    if status not in (APPROVED, REJECTED):
        raise AdminError(f"status must be {APPROVED!r} or {REJECTED!r}")

    with _queue_lock:
        entries = read_all()
        entry = _find(entries, submission_id)
        if entry is None:
            raise AdminError(f"No submission with id {submission_id!r}", status=404)
        if entry.get("status") != PENDING:
            raise AdminError(
                f"Submission {submission_id!r} was already {entry.get('status')}", status=409)

        entry["status"] = status
        entry["decided_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        if note:
            entry["note"] = note
        _write_all(entries)

    logger.info("Submission %s %s", submission_id, status)
    return entry


def decide_reset(submission_id):
    """Put a submission back to pending.

    Used when an approval fails downstream — the catalogue changed and the
    name is now taken, say. Leaving it marked approved would lose the
    proposal entirely.
    """
    with _queue_lock:
        entries = read_all()
        entry = _find(entries, submission_id)
        if entry is None:
            return None
        entry["status"] = PENDING
        entry.pop("decided_at", None)
        _write_all(entries)
    return entry


def pending_count():
    return len(read_all(status=PENDING))


__all__ = ["PENDING", "APPROVED", "REJECTED", "EDITABLE_FIELDS",
           "read_all", "submit", "decide", "decide_reset", "pending_count"]
