"""
PublishService — orchestrates the DRAFT → PUBLISHED transition.

GOVERNANCE INVARIANTS ENFORCED:
  INV-001  A set with zero active questions cannot be published.
  INV-002  A set without a title cannot be published.
  INV-003  A set without a category cannot be published.
  INV-004  Publishing creates a new AssessmentSetVersion — it never mutates
           an existing version.
  INV-005  Identical content (same checksum) does not create a duplicate
           version — idempotent for retries.
  INV-006  AssessmentSetVersion rows are immutable after creation; the
           model's save() override enforces this.
  INV-007  Every state transition (publish, idempotent publish, validation
           failure) MUST emit a GovernanceEvent for the audit trail.
  INV-008  Each new version records its predecessor (previous_version FK)
           to form a complete lineage chain.
  INV-009  Full publish validation runs before snapshot creation so a
           structurally invalid set can never produce a published version.

ROLLBACK SAFETY:
  - This function is @transaction.atomic. If anything fails after version
    creation but before the caller returns, the version row AND governance
    events are rolled back together.
  - GovernanceEvent emission failures are logged but do NOT roll back the
    transaction — audit failure must not block publish.
  - Old workers that don't know about set_version still work: the FK is
    nullable and old code paths fall back to live question lookup.

CONCURRENCY:
  - select_for_update() on the AssessmentSet row prevents two concurrent
    publish calls from creating duplicate versions for the same set.
  - The (assessment_set, snapshot_checksum) unique constraint is the DB-level
    guard for idempotency races.
  - version_number determination happens INSIDE the locked transaction so
    the MAX() query sees the committed state after the lock is acquired.
"""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from .snapshot_builder import build_snapshot, compute_checksum
from .publish_validator import validate_for_publish, ValidationSeverity
from .governance_events import emit_governance_event


class PublishValidationError(Exception):
    """Raised when publish preconditions are not met. HTTP 400 equivalent."""

    def __init__(
        self,
        message: str,
        code: str = "publish_validation_error",
        findings: list | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.findings = findings or []  # list[ValidationFinding] for structured errors


def publish_assessment_set(
    *,
    set_id: int,
    actor,  # AUTH_USER_MODEL instance or None (None = system/backfill)
    correlation_id: str = "",
) -> "AssessmentSetVersion":  # noqa: F821
    """
    Publish an AssessmentSet: validate, build snapshot, create immutable version.

    Args:
        set_id:         PK of the AssessmentSet to publish.
        actor:          User performing the publish action (for audit trail).
                        Pass None for system-generated backfills.
        correlation_id: HTTP request trace ID for governance event linking.

    Returns:
        The newly created AssessmentSetVersion (HTTP 201), or the existing
        identical version if content has not changed since last publish
        (HTTP 200 — idempotent retry safety).

    Raises:
        PublishValidationError: if preconditions are not met (HTTP 400).
        AssessmentSet.DoesNotExist: if set_id is invalid (HTTP 404).

    TRANSACTION ARCHITECTURE:
        The actual publish work runs in an inner @transaction.atomic block
        (_publish_atomic). If validation fails, the inner block rolls back
        and we emit the governance event HERE, in the outer (non-atomic)
        scope. This ensures validation-failure events always persist even
        though the failed transaction rolled them back.
    """
    try:
        return _publish_atomic(set_id=set_id, actor=actor, correlation_id=correlation_id)
    except PublishValidationError as exc:
        # Inner transaction has been rolled back. Emit the failure event now
        # in a clean non-transactional context — this write WILL commit.
        from assessments.models import GovernanceEvent
        emit_governance_event(
            event_type=GovernanceEvent.EVENT_PUBLISH_VALIDATION_FAILED,
            actor=actor,
            entity_type="AssessmentSet",
            entity_id=set_id,
            payload={
                "blocking_count": len(exc.findings),
                "findings": [f.to_dict() for f in exc.findings[:10]],
                "first_code": exc.code,
            },
            correlation_id=correlation_id,
        )
        raise


@transaction.atomic
def _publish_atomic(
    *,
    set_id: int,
    actor,
    correlation_id: str = "",
) -> "AssessmentSetVersion":  # noqa: F821
    """
    Internal: the transactional body of publish_assessment_set.

    Called by publish_assessment_set() which handles post-rollback event
    emission for validation failures.
    """
    from assessments.models import AssessmentSet, AssessmentSetVersion, AssessmentQuestion, GovernanceEvent

    # ── Lock the set row ───────────────────────────────────────────────────────
    # select_for_update() serializes concurrent publish calls for the same set.
    # Two simultaneous publishes will queue — the second sees the first's
    # committed version_number and creates the correct next_version_number.
    aset = (
        AssessmentSet.objects.select_for_update()
        .filter(pk=set_id)
        .first()
    )
    if not aset:
        raise AssessmentSet.DoesNotExist(f"AssessmentSet #{set_id} not found.")

    # ── Full publish validation ────────────────────────────────────────────────
    # Run INSIDE the locked transaction for a stable question set.
    active_questions = list(
        AssessmentQuestion.objects.filter(
            assessment_set=aset, is_active=True
        ).order_by("order", "id")
    )

    report = validate_for_publish(aset, active_questions)

    if not report.is_publishable:
        # Raise here — the outer publish_assessment_set() will catch this and
        # emit the validation-failure governance event AFTER this transaction
        # rolls back (so the event persists).
        first = report.blocking_findings[0]
        raise PublishValidationError(
            first.message,
            code=first.code,
            findings=report.blocking_findings,
        )

    # ── Build snapshot ─────────────────────────────────────────────────────────
    # build_snapshot uses the same active_questions list — stable inside the lock.
    snapshot = build_snapshot(aset)
    checksum = compute_checksum(snapshot)

    # ── Idempotency: identical content → return existing version ───────────────
    # Guards against HTTP retry storms where the commit succeeded but the
    # response was lost.
    try:
        existing = AssessmentSetVersion.objects.get(
            assessment_set=aset,
            snapshot_checksum=checksum,
        )
        # Ensure the set is active (could have been archived since last publish).
        if not aset.is_active:
            aset.is_active = True
            aset.save(update_fields=["is_active", "updated_at"])

        emit_governance_event(
            event_type=GovernanceEvent.EVENT_PUBLISH_IDEMPOTENT,
            actor=actor,
            entity_type="AssessmentSetVersion",
            entity_id=existing.pk,
            payload={
                "set_id": aset.pk,
                "version_number": existing.version_number,
                "checksum": checksum[:16],
                "reason": "identical_content",
            },
            correlation_id=correlation_id,
        )
        return existing
    except AssessmentSetVersion.DoesNotExist:
        pass

    # ── Determine previous version (for lineage chain) ─────────────────────────
    previous_version = (
        AssessmentSetVersion.objects.filter(assessment_set=aset)
        .order_by("-version_number")
        .first()
    )
    next_version_number = (previous_version.version_number if previous_version else 0) + 1

    # ── Create immutable version ───────────────────────────────────────────────
    version = AssessmentSetVersion(
        assessment_set=aset,
        version_number=next_version_number,
        snapshot_json=snapshot,
        snapshot_checksum=checksum,
        question_count=len(active_questions),
        previous_version=previous_version,  # lineage chain
        published_by=actor if (actor and getattr(actor, "is_authenticated", False)) else None,
        published_at=timezone.now(),
    )
    version.save()  # AssessmentSetVersion.save() rejects updates — only INSERT.

    # ── Mark the set as published / active ────────────────────────────────────
    aset.is_active = True
    aset.save(update_fields=["is_active", "updated_at"])

    # ── Governance events ──────────────────────────────────────────────────────
    # 1. Publish event on the new version (primary audit record).
    emit_governance_event(
        event_type=GovernanceEvent.EVENT_PUBLISH,
        actor=actor,
        entity_type="AssessmentSetVersion",
        entity_id=version.pk,
        payload={
            "set_id": aset.pk,
            "set_title": aset.title,
            "version_number": next_version_number,
            "question_count": version.question_count,
            "checksum": checksum[:16],
            "previous_version_id": previous_version.pk if previous_version else None,
            "warning_count": len(report.warning_findings),
            "warnings": [f.to_dict() for f in report.warning_findings[:5]],
        },
        correlation_id=correlation_id,
    )

    # 2. Supersede event on the predecessor (for lineage visibility).
    if previous_version:
        emit_governance_event(
            event_type=GovernanceEvent.EVENT_SUPERSEDE,
            actor=actor,
            entity_type="AssessmentSetVersion",
            entity_id=previous_version.pk,
            payload={
                "set_id": aset.pk,
                "superseded_by_version_id": version.pk,
                "superseded_by_version_number": next_version_number,
            },
            correlation_id=correlation_id,
        )

    return version
