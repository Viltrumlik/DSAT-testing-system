"""
SnapshotCompat — forward-compatible snapshot schema registry.

DESIGN PRINCIPLES:
  1. Stored snapshots are NEVER mutated. Compatibility is achieved by
     in-memory adaptation (upgrade) when reading old versions.

  2. All historical schema versions must remain supported indefinitely.
     The stored snapshot_json["schema_version"] is the permanent record
     of which schema was in effect at publish time.

  3. Grading, review, and bundle-delivery code targets CURRENT_SCHEMA_VERSION.
     Old snapshots are adapted at read-time before processing.

  4. Adding optional fields with defaults is a schema-compatible change
     (no version bump required). Removing fields, renaming fields, or
     changing semantics of existing fields requires a version bump and
     a migration function in _MIGRATIONS.

COMPATIBILITY POLICY:
  - Every snapshot from schema_version=1 to CURRENT_SCHEMA_VERSION
    must be upgradeable to CURRENT_SCHEMA_VERSION via the migration chain.
  - Migration functions are pure: they take an old dict and return a new
    dict. They MUST set snapshot_json["schema_version"] to the next version.
  - The adapt_snapshot() function applies the chain automatically.

CURRENT SCHEMA (version 1):
  {
    "schema_version": 1,
    "set_id": int,
    "set_title": str,
    "set_subject": "math" | "english",
    "set_category": str,
    "set_description": str,
    "question_count": int,
    "questions": [
      {
        "id": int,
        "order": int,
        "prompt": str,
        "question_type": str,
        "choices": list,
        "correct_answer": any,
        "grading_config": dict,
        "points": int,
      }
    ]
  }

DEPRECATION POLICY:
  - When CURRENT_SCHEMA_VERSION is bumped, the old version is deprecated
    (still readable, never writable).
  - Deprecation is announced in the changelog with a migration deadline.
  - After the deadline, old snapshot reading may be removed from the live
    code path but MUST be preserved in the integrity-check tooling.
"""

from __future__ import annotations

from typing import Any, Callable

# Bump this only for breaking schema changes. See DEPRECATION POLICY above.
CURRENT_SCHEMA_VERSION = 1

# ── Migration registry ─────────────────────────────────────────────────────
# Maps: source_version → migration_function(snap: dict) -> dict
# Chain: 1 → 2 → ... → CURRENT_SCHEMA_VERSION
# A missing entry for version N means N → N+1 is not yet defined (future).
_MIGRATIONS: dict[int, Callable[[dict[str, Any]], dict[str, Any]]] = {
    # Example — uncomment and implement when v2 is introduced:
    # 1: _migrate_v1_to_v2,
}


# ── Public API ─────────────────────────────────────────────────────────────

def adapt_snapshot(snapshot_json: dict[str, Any]) -> dict[str, Any]:
    """
    Upgrade snapshot_json to CURRENT_SCHEMA_VERSION in-memory.

    Returns a new dict — the original is NEVER mutated.

    Raises:
        ValueError: if schema_version is missing, negative, or requires
                    a downgrade (snapshot is newer than this code).
        LookupError: if a migration function is missing in the chain.
    """
    version = snapshot_json.get("schema_version")
    if not isinstance(version, int) or version < 1:
        raise ValueError(
            f"Snapshot has invalid schema_version: {version!r}. "
            "Expected a positive integer."
        )
    if version > CURRENT_SCHEMA_VERSION:
        raise ValueError(
            f"Snapshot schema_version={version} is newer than "
            f"CURRENT_SCHEMA_VERSION={CURRENT_SCHEMA_VERSION}. "
            "Deploy newer application code before reading this snapshot."
        )
    if version == CURRENT_SCHEMA_VERSION:
        return snapshot_json  # already current — return as-is (no copy needed)

    snap = dict(snapshot_json)  # shallow copy; do NOT mutate the original

    while snap.get("schema_version", 0) < CURRENT_SCHEMA_VERSION:
        v = snap["schema_version"]
        migrate_fn = _MIGRATIONS.get(v)
        if migrate_fn is None:
            raise LookupError(
                f"No migration function registered for schema_version={v} → {v + 1}. "
                f"Add an entry to snapshot_compat._MIGRATIONS."
            )
        snap = migrate_fn(snap)
        # Safety: migration function MUST advance the version.
        if snap.get("schema_version", 0) <= v:
            raise RuntimeError(
                f"Migration function for v{v} did not advance schema_version."
            )

    return snap


def can_grade_snapshot(snapshot_json: dict[str, Any]) -> tuple[bool, str]:
    """
    Quick compatibility check — call before adapt_snapshot() in hot paths.

    Returns:
        (True, "ok")  — snapshot can be graded with current code.
        (False, reason_str)  — cannot grade; reason explains the problem.
    """
    version = snapshot_json.get("schema_version") if isinstance(snapshot_json, dict) else None
    if not isinstance(version, int) or version < 1:
        return False, f"Missing or invalid schema_version: {version!r}"
    if version > CURRENT_SCHEMA_VERSION:
        return False, (
            f"Snapshot schema_version={version} requires newer application code "
            f"(CURRENT_SCHEMA_VERSION={CURRENT_SCHEMA_VERSION})."
        )
    # Walk the migration chain to confirm it's complete.
    v = version
    while v < CURRENT_SCHEMA_VERSION:
        if v not in _MIGRATIONS:
            return False, (
                f"No migration path from schema_version={v} to "
                f"{CURRENT_SCHEMA_VERSION}."
            )
        v += 1
    return True, "ok"


def validate_snapshot_structure(snapshot_json: dict[str, Any]) -> list[str]:
    """
    Deep structural validation of a snapshot dict.

    Returns a list of error strings. An empty list means the snapshot
    is structurally valid for the declared schema_version.

    Use this in integrity checks and the publish flow, not in hot
    grading paths (prefer can_grade_snapshot() there).
    """
    if not isinstance(snapshot_json, dict):
        return ["Snapshot root is not a dict."]

    errors: list[str] = []

    # ── Top-level required fields ──────────────────────────────────────────
    required_top = ("schema_version", "set_id", "set_title", "questions")
    for field in required_top:
        if field not in snapshot_json:
            errors.append(f"Missing required top-level field: {field!r}")
    if errors:
        return errors  # cannot go further safely

    version = snapshot_json["schema_version"]
    if not isinstance(version, int) or version < 1:
        errors.append(f"schema_version must be a positive int; got {version!r}")

    if not isinstance(snapshot_json["set_id"], int):
        errors.append("set_id must be an int")

    questions = snapshot_json["questions"]
    if not isinstance(questions, list):
        errors.append("'questions' must be a list")
        return errors

    # ── Per-question structure ─────────────────────────────────────────────
    required_q_fields = ("id", "prompt", "question_type")
    seen_q_ids: set[int] = set()
    for i, q in enumerate(questions):
        if not isinstance(q, dict):
            errors.append(f"questions[{i}] is not a dict")
            continue
        for qf in required_q_fields:
            if qf not in q:
                errors.append(f"questions[{i}] missing required field: {qf!r}")
        qid = q.get("id")
        if isinstance(qid, int):
            if qid in seen_q_ids:
                errors.append(f"questions[{i}] duplicate question id={qid}")
            seen_q_ids.add(qid)

    return errors
