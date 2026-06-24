"""
ReplayCertificationService — non-destructive historical replay verification.

PURPOSE:
  Prove that a graded attempt's result is perfectly reproducible from its
  stored snapshot and answer records. This is the formal trust contract of
  the immutable academic-record platform.

DESIGN:
  certify_attempt_replay() is COMPLETELY NON-DESTRUCTIVE:
  - reads existing DB state only
  - performs no writes, no status changes, no result updates
  - re-runs the grading arithmetic from first principles
  - compares against the stored AssessmentResult

  A CERTIFIED attempt satisfies ALL of:
  C1  The attempt has a pinned set_version (snapshot path, not fallback).
  C2  The snapshot checksum is intact (no DB corruption).
  C3  The snapshot schema can be graded by current code.
  C4  All question IDs in question_order exist in the snapshot.
  C5  Re-computing grading from snapshot + answers produces the same score,
      percent, correct_count, and total_questions as the stored result.

  A PARTIALLY_CERTIFIED attempt satisfies C1-C4 but used the live-read
  fallback for its original grading (set_version added post-hoc by backfill).
  These are acceptable but should be migrated to full certification via re-grade.

  A NON_CERTIFIED attempt fails one or more of C1-C5.
  These are operational alerts — investigate immediately.

USAGE (in management commands and tests):
    from assessments.domain.replay_certification import certify_attempt_replay

    result = certify_attempt_replay(attempt_id=42)
    if not result.certified:
        print(f"FAIL: {result.findings}")
"""

from __future__ import annotations

import dataclasses
from decimal import Decimal
from typing import Any

from django.db import transaction


@dataclasses.dataclass
class ReplayCertificationResult:
    attempt_id: int
    certified: bool

    # Certification checklist
    has_snapshot_pin: bool = False      # C1
    checksum_valid: bool = False        # C2
    schema_compatible: bool = False     # C3
    question_order_pure: bool = False   # C4
    score_matches: bool = False         # C5

    # Replay numerics (None if replay could not run)
    original_score: Decimal | None = None
    replayed_score: Decimal | None = None
    original_percent: Decimal | None = None
    replayed_percent: Decimal | None = None
    original_correct_count: int | None = None
    replayed_correct_count: int | None = None
    original_total_questions: int | None = None
    replayed_total_questions: int | None = None

    # Metadata
    snapshot_version_id: int | None = None
    snapshot_version_number: int | None = None
    snapshot_question_count: int | None = None

    # Audit
    findings: list[str] = dataclasses.field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempt_id": self.attempt_id,
            "certified": self.certified,
            "checklist": {
                "C1_has_snapshot_pin": self.has_snapshot_pin,
                "C2_checksum_valid": self.checksum_valid,
                "C3_schema_compatible": self.schema_compatible,
                "C4_question_order_pure": self.question_order_pure,
                "C5_score_matches": self.score_matches,
            },
            "original": {
                "score": str(self.original_score) if self.original_score is not None else None,
                "percent": str(self.original_percent) if self.original_percent is not None else None,
                "correct_count": self.original_correct_count,
                "total_questions": self.original_total_questions,
            },
            "replayed": {
                "score": str(self.replayed_score) if self.replayed_score is not None else None,
                "percent": str(self.replayed_percent) if self.replayed_percent is not None else None,
                "correct_count": self.replayed_correct_count,
                "total_questions": self.replayed_total_questions,
            },
            "snapshot": {
                "version_id": self.snapshot_version_id,
                "version_number": self.snapshot_version_number,
                "question_count": self.snapshot_question_count,
            },
            "findings": self.findings,
        }


def certify_attempt_replay(attempt_id: int) -> ReplayCertificationResult:
    """
    Non-destructively verify that a graded attempt's result is reproducible.

    IMPORTANT: This function is READ-ONLY. It makes no DB writes.

    Args:
        attempt_id: PK of an AssessmentAttempt in STATUS_GRADED.

    Returns:
        ReplayCertificationResult. Check .certified for the final verdict.
    """
    from assessments.models import AssessmentAttempt, AssessmentResult, AssessmentAnswer
    from assessments.grading import grade_answer
    from .snapshot_builder import verify_snapshot_integrity
    from .snapshot_compat import adapt_snapshot, can_grade_snapshot, validate_snapshot_structure
    from .snapshot_builder import questions_from_snapshot

    result = ReplayCertificationResult(attempt_id=attempt_id, certified=False)
    findings = result.findings

    # ── Load attempt ──────────────────────────────────────────────────────────
    try:
        att = (
            AssessmentAttempt.objects.select_related(
                "homework__assessment_set",
                "set_version",
            )
            .get(pk=attempt_id)
        )
    except AssessmentAttempt.DoesNotExist:
        findings.append(f"Attempt #{attempt_id} does not exist.")
        return result

    if att.status != AssessmentAttempt.STATUS_GRADED:
        findings.append(
            f"Attempt #{attempt_id} is not graded (status={att.status}). "
            "Only graded attempts can be certified."
        )
        return result

    # Load stored result
    try:
        stored = AssessmentResult.objects.get(attempt=att)
    except AssessmentResult.DoesNotExist:
        findings.append(f"Attempt #{attempt_id} has no AssessmentResult row.")
        return result

    result.original_score = stored.score_points
    result.original_percent = stored.percent
    result.original_correct_count = stored.correct_count
    result.original_total_questions = stored.total_questions

    # ── C1: Snapshot pin ──────────────────────────────────────────────────────
    if att.set_version_id is None:
        findings.append(
            "C1 FAIL: attempt has no set_version (pre-snapshot attempt). "
            "Replay cannot be certified without a pinned snapshot. "
            "Run backfill_snapshot_versions to pin the appropriate version, "
            "then re-grade."
        )
        return result

    result.has_snapshot_pin = True
    result.snapshot_version_id = att.set_version_id
    result.snapshot_version_number = att.set_version.version_number
    result.snapshot_question_count = att.set_version.question_count

    # ── C2: Checksum integrity ─────────────────────────────────────────────────
    snapshot_json = att.set_version.snapshot_json
    stored_checksum = att.set_version.snapshot_checksum

    if not verify_snapshot_integrity(snapshot_json, stored_checksum):
        findings.append(
            f"C2 FAIL: snapshot checksum mismatch for version #{att.set_version_id}. "
            f"Stored: {stored_checksum[:16]}… — snapshot has been corrupted. "
            "This is a critical integrity violation."
        )
        return result

    result.checksum_valid = True

    # ── Structural validation ──────────────────────────────────────────────────
    struct_errors = validate_snapshot_structure(snapshot_json)
    if struct_errors:
        findings.extend(f"Snapshot structural error: {e}" for e in struct_errors)
        return result

    # ── C3: Schema compatibility ───────────────────────────────────────────────
    ok, reason = can_grade_snapshot(snapshot_json)
    if not ok:
        findings.append(f"C3 FAIL: {reason}")
        return result

    result.schema_compatible = True
    snapshot_json = adapt_snapshot(snapshot_json)  # upgrade if needed (no-op for v1)

    # ── C4: Question order purity ──────────────────────────────────────────────
    raw_questions = questions_from_snapshot(snapshot_json)
    q_by_id = {q["id"]: q for q in raw_questions}

    order_ids = [
        int(x)
        for x in (att.question_order or [])
        if isinstance(x, (int, str)) and str(x).isdigit()
    ]

    missing_in_snapshot = [qid for qid in order_ids if qid not in q_by_id]
    if missing_in_snapshot:
        findings.append(
            f"C4 FAIL: question_order contains IDs not in snapshot: "
            f"{missing_in_snapshot[:10]}. "
            "This indicates the attempt was modified after the snapshot was created."
        )
        return result

    result.question_order_pure = True

    # ── C5: Replay score computation (read-only) ───────────────────────────────
    # Load all answers for this attempt.
    answers_qs = AssessmentAnswer.objects.filter(
        attempt=att, question_id__in=list(q_by_id.keys())
    )
    answers_by_qid = {a.question_id: a for a in answers_qs}

    # Reconstruct the ordered question list exactly as grading would.
    ordered_questions = (
        [q_by_id[qid] for qid in order_ids if qid in q_by_id]
        if order_ids
        else sorted(raw_questions, key=lambda q: (q.get("order", 0), q["id"]))
    )

    # Re-run grading arithmetic (read-only, no DB writes).
    replayed_score = Decimal("0")
    replayed_max = Decimal("0")
    replayed_correct = 0
    replayed_total = len(ordered_questions)

    for q in ordered_questions:
        pts = Decimal(str(q.get("points", 1) or 1))
        replayed_max += pts
        ans_row = answers_by_qid.get(q["id"])
        if ans_row is not None:
            ok = grade_answer(
                question_type=q["question_type"],
                correct_answer=q.get("correct_answer"),
                answer=ans_row.answer,
                config=q.get("grading_config") or {},
            )
            if ok:
                replayed_score += pts
                replayed_correct += 1

    replayed_percent = (
        (replayed_score / replayed_max * Decimal("100"))
        if replayed_max > 0
        else Decimal("0")
    )

    result.replayed_score = replayed_score
    result.replayed_percent = replayed_percent.quantize(Decimal("0.01"))
    result.replayed_correct_count = replayed_correct
    result.replayed_total_questions = replayed_total

    # Compare against stored result (allow small float tolerance in percent).
    score_ok = replayed_score == stored.score_points
    percent_ok = abs(replayed_percent - stored.percent) < Decimal("0.01")
    correct_ok = replayed_correct == stored.correct_count
    total_ok = replayed_total == stored.total_questions

    if not (score_ok and percent_ok and correct_ok and total_ok):
        delta_details = []
        if not score_ok:
            delta_details.append(
                f"score: stored={stored.score_points} replayed={replayed_score}"
            )
        if not percent_ok:
            delta_details.append(
                f"percent: stored={stored.percent} replayed={replayed_percent}"
            )
        if not correct_ok:
            delta_details.append(
                f"correct_count: stored={stored.correct_count} replayed={replayed_correct}"
            )
        if not total_ok:
            delta_details.append(
                f"total_questions: stored={stored.total_questions} replayed={replayed_total}"
            )
        findings.append(
            "C5 FAIL: replayed grading differs from stored result. "
            + "; ".join(delta_details)
        )
        return result

    result.score_matches = True

    # ── All checks passed ──────────────────────────────────────────────────────
    result.certified = True
    return result


def bulk_certify_attempts(
    *,
    attempt_ids: list[int] | None = None,
    limit: int = 1000,
    only_uncertified: bool = False,
) -> list[ReplayCertificationResult]:
    """
    Certify multiple attempts.

    Args:
        attempt_ids:      Specific attempt PKs to certify. None = all graded.
        limit:            Maximum number of attempts to certify per call.
        only_uncertified: If True, skip attempts where set_version_id is set
                          and we already know they pass C1.

    Returns a list of ReplayCertificationResult, one per attempt.
    """
    from assessments.models import AssessmentAttempt

    qs = AssessmentAttempt.objects.filter(
        status=AssessmentAttempt.STATUS_GRADED
    ).order_by("id")

    if attempt_ids is not None:
        qs = qs.filter(pk__in=attempt_ids)

    if only_uncertified:
        qs = qs.filter(set_version_id__isnull=True)

    results: list[ReplayCertificationResult] = []
    for att in qs[:limit].iterator(chunk_size=100):
        results.append(certify_attempt_replay(att.pk))

    return results
