"""
SnapshotBuilder — deterministic, self-sufficient snapshot generation.

DESIGN PRINCIPLES:
  1. Self-sufficient: the snapshot JSON must contain everything required to
     render an exam, grade answers, reproduce a review page, and audit a
     historical result — with ZERO live database lookups after creation.

  2. Deterministic: given the same input, always produces the same JSON and
     the same checksum. Questions are ordered by (order, id) — stable sort.

  3. Schema-versioned: every snapshot carries a schema_version field so
     consumers can handle format evolution without breaking historical records.

  4. Checksum-stable: SHA-256 of canonical JSON (keys sorted, no whitespace,
     UTF-8). Used for idempotency (don't create duplicate versions) and
     integrity verification.

SNAPSHOT SCHEMA (version 1):
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
      },
      ...
    ]
  }
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from assessments.models import AssessmentSet

# Bump this when the snapshot schema changes in a backward-incompatible way.
# Consumers must check schema_version before parsing.
SNAPSHOT_SCHEMA_VERSION = 1


def build_snapshot(assessment_set: "AssessmentSet") -> dict[str, Any]:
    """
    Build a complete, self-sufficient snapshot dict for an AssessmentSet.

    Reads ONLY active questions (is_active=True), ordered by (order, id).
    This is the canonical ordering for exam delivery and grading.

    IMPORTANT: call this inside the same transaction that creates the
    AssessmentSetVersion row so the question set is stable at snapshot time.
    """
    # Import here to avoid circular import; models import domain too.
    from assessments.models import AssessmentQuestion

    questions = list(
        AssessmentQuestion.objects.filter(
            assessment_set=assessment_set,
            is_active=True,
        )
        .select_related("bank_question", "bank_version")
        .order_by("order", "id")
    )

    questions_data: list[dict[str, Any]] = []
    for q in questions:
        entry = {
            "id": q.id,
            "order": q.order,
            "prompt": q.prompt,
            "question_type": q.question_type,
            # choices and correct_answer are JSONField — already plain Python
            "choices": q.choices if q.choices is not None else [],
            "correct_answer": q.correct_answer,
            "grading_config": q.grading_config if q.grading_config else {},
            "points": q.points,
        }
        # M4 FREEZE: pin the Question Bank source so future bank edits cannot alter
        # this historical snapshot. Added ONLY when a bank link exists, so
        # assessments authored without the bank produce byte-identical snapshots
        # (and identical checksums) to before — zero behaviour change for them.
        if q.bank_question_id:
            entry["bank_qb_id"] = q.bank_question.qb_id
            entry["bank_version_number"] = (
                q.bank_version.version_number if q.bank_version_id else None
            )
        questions_data.append(entry)

    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "set_id": assessment_set.id,
        "set_title": assessment_set.title,
        "set_subject": assessment_set.subject,
        "set_category": assessment_set.category or "",
        "set_description": assessment_set.description or "",
        "question_count": len(questions_data),
        "questions": questions_data,
    }


def compute_checksum(snapshot_json: dict[str, Any]) -> str:
    """
    SHA-256 of the canonical JSON representation.

    Canonical form: keys sorted recursively, no extra whitespace, ASCII-safe.
    This is stable across Python versions and JSON library implementations.
    """
    canonical = json.dumps(
        snapshot_json,
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def questions_from_snapshot(snapshot_json: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Extract the questions list from a snapshot dict.

    Returns an empty list if the snapshot is malformed — callers must handle
    the empty-list case gracefully (fall back to live lookup or raise).
    """
    if not isinstance(snapshot_json, dict):
        return []
    return snapshot_json.get("questions") or []


def verify_snapshot_integrity(snapshot_json: dict[str, Any], stored_checksum: str) -> bool:
    """
    Recompute the checksum and compare to the stored value.

    Use this in integrity-check management commands and ops tooling.
    Returns True if the snapshot is intact, False if it has been corrupted.
    """
    return compute_checksum(snapshot_json) == stored_checksum
