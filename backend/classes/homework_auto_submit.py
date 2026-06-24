"""
When a student finishes all practice-test sections required by class homework, upsert the
submission as SUBMITTED with a linked TestAttempt — no separate file upload.

Also handles assessment homework: when a student submits an AssessmentAttempt,
upsert the class Submission so the grading UI shows it.

Also used when loading ``my-submission`` so late joins / missed signals still sync.
"""

from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

from exams.models import TestAttempt

from .models import (
    Assignment,
    ClassroomMembership,
    Submission,
    SubmissionAuditEvent,
    SubmissionReview,
    assignment_target_practice_test_ids,
)
from .submission_audit import audit_submission_event


def _auto_grade(s: Submission, assignment: Assignment, grade, max_score, source: str, rev: int) -> None:
    """Create/update the automatic grade and move the submission straight to REVIEWED.

    Auto grades (objective tests/assessments) never sit in the teacher's manual queue.
    Recorded grader is the assignment author; ``is_auto=True`` marks it as machine-graded.
    """
    SubmissionReview.objects.update_or_create(
        submission=s,
        defaults={
            "teacher": assignment.created_by,
            "grade": grade,
            "max_score": max_score,
            "is_auto": True,
        },
    )
    prev_status = s.status
    s.status = Submission.STATUS_REVIEWED
    if s.submitted_at is None:
        s.submitted_at = timezone.now()
    s.returned_at = None
    s.return_note = ""
    audit_submission_event(
        s.pk, None, SubmissionAuditEvent.EVENT_REVIEW_UPSERT,
        {"source": source, "auto": True, "grade": str(grade)}, submission_revision=rev,
    )
    if prev_status != s.status:
        audit_submission_event(
            s.pk, None, SubmissionAuditEvent.EVENT_STATUS_CHANGE,
            {"from": prev_status, "to": s.status, "source": source}, submission_revision=rev,
        )

logger = logging.getLogger("classes.homework_auto_submit")


def _latest_completed_attempt(student_id: int, practice_test_id: int) -> TestAttempt | None:
    return (
        TestAttempt.objects.filter(
            student_id=student_id,
            practice_test_id=practice_test_id,
            is_completed=True,
        )
        .order_by("-submitted_at", "-id")
        .first()
    )


def _collect_completed_attempts_for_targets(
    student_id: int, targets: list[int]
) -> list[TestAttempt] | None:
    out: list[TestAttempt] = []
    for pt_id in targets:
        ta = _latest_completed_attempt(student_id, pt_id)
        if not ta:
            return None
        out.append(ta)
    return out


def _representative_attempt(attempts: list[TestAttempt]) -> TestAttempt:
    return max(attempts, key=lambda a: (a.submitted_at or timezone.now(), a.pk))


def _apply_sync(student, assignment: Assignment, best: TestAttempt, total_score) -> bool:
    """
    Link ``best`` and finalize the submission. Practice/SAT homework is auto-graded:
    the submission moves straight to REVIEWED with an automatic grade (``total_score``),
    so it never enters the teacher's manual grading queue. Returns True if the row changed.
    """
    from django.db import IntegrityError

    SOURCE = "practice_targets_complete"
    with transaction.atomic():
        row = (
            Submission.objects.select_for_update()
            .filter(assignment=assignment, student=student)
            .first()
        )
        if row is None:
            try:
                row = Submission.objects.create(assignment=assignment, student=student)
            except IntegrityError:
                row = Submission.objects.select_for_update().get(
                    assignment=assignment, student=student
                )

        s = Submission.objects.select_for_update().get(pk=row.pk)

        existing_review = SubmissionReview.objects.filter(submission=s).first()
        manual_review = existing_review is not None and not existing_review.is_auto
        # Never overwrite a human teacher's grade.
        if s.status == Submission.STATUS_REVIEWED and manual_review:
            return False

        prev_attempt_id = s.attempt_id
        attempt_changed = prev_attempt_id != best.id
        auto = assignment.is_auto_graded

        # Already auto-graded on this exact attempt → nothing to do.
        if s.status == Submission.STATUS_REVIEWED and not attempt_changed:
            return False
        if s.status == Submission.STATUS_SUBMITTED and not attempt_changed and not auto:
            return False

        s.revision += 1
        rev = s.revision
        if attempt_changed:
            audit_submission_event(
                s.pk, None, SubmissionAuditEvent.EVENT_ATTEMPT_CHANGE,
                {"from_attempt_id": prev_attempt_id, "to_attempt_id": best.id, "source": SOURCE},
                submission_revision=rev,
            )
        s.attempt = best

        if auto:
            _auto_grade(s, assignment, total_score, None, SOURCE, rev)
        else:
            # Fallback (no auto-grade signal): finalize as submitted for manual review.
            if s.status in (Submission.STATUS_DRAFT, Submission.STATUS_RETURNED):
                prev_for_status = s.status
                s.mark_submitted()
                audit_submission_event(
                    s.pk, None, SubmissionAuditEvent.EVENT_STATUS_CHANGE,
                    {"from": prev_for_status, "to": s.status, "source": SOURCE},
                    submission_revision=rev,
                )
        s.save()
        return True


def sync_practice_submission_for_assignment(student, assignment: Assignment) -> bool:
    """
    If every practice-test target for ``assignment`` has a completed attempt for ``student``,
    ensure the class submission is SUBMITTED with a linked attempt.
    """
    # Multi-content bundles are instructional: each part scores in its own engine, but the
    # classroom submission is not auto-finalized from a single signal (the practice-sync and
    # assessment-sync paths would otherwise race on one SubmissionReview).
    if assignment.is_multi_content:
        return False
    targets = assignment_target_practice_test_ids(assignment)
    if not targets:
        return False
    attempts = _collect_completed_attempts_for_targets(student.pk, targets)
    if not attempts:
        return False
    best = _representative_attempt(attempts)
    # Auto grade = total scaled score across all required sections (real recorded scores).
    total_score = sum(a.score for a in attempts if a.score is not None)
    try:
        return _apply_sync(student, assignment, best, total_score)
    except Exception:
        logger.exception(
            "sync_practice_submission_failed assignment_id=%s student_id=%s",
            assignment.pk,
            getattr(student, "pk", student),
        )
        raise


def sync_homework_after_test_attempt_saved(attempt: TestAttempt) -> None:
    """Called from post_save when ``is_completed`` is True."""
    if not attempt.is_completed:
        return
    student_id = attempt.student_id
    class_ids = ClassroomMembership.objects.filter(
        user_id=student_id, role=ClassroomMembership.ROLE_STUDENT
    ).values_list("classroom_id", flat=True)
    if not class_ids:
        return

    from django.contrib.auth import get_user_model

    User = get_user_model()
    student = User.objects.filter(pk=student_id).first()
    if not student:
        return

    for assignment in Assignment.objects.filter(classroom_id__in=class_ids).iterator():
        targets = assignment_target_practice_test_ids(assignment)
        if not targets or attempt.practice_test_id not in targets:
            continue
        try:
            sync_practice_submission_for_assignment(student, assignment)
        except Exception:
            logger.exception(
                "sync_homework_after_attempt assignment_id=%s attempt_id=%s",
                assignment.pk,
                attempt.pk,
            )


# ---------------------------------------------------------------------------
# Assessment homework → class Submission sync
# ---------------------------------------------------------------------------


def sync_assessment_submission(assessment_attempt) -> bool:
    """
    When an AssessmentAttempt is submitted (or graded), create/update the
    linked class Submission so the grading UI shows it.

    ``assessment_attempt`` is an ``assessments.AssessmentAttempt`` instance.
    The chain is: AssessmentAttempt → homework (HomeworkAssignment) → assignment (classes.Assignment).
    """
    from assessments.models import AssessmentAttempt  # avoid circular import

    hw = getattr(assessment_attempt, "homework", None)
    if hw is None:
        return False

    assignment = getattr(hw, "assignment", None)
    if assignment is None:
        return False

    # Multi-content bundles are instructional — do not auto-finalize from the assessment signal.
    if assignment.is_multi_content:
        return False

    student = assessment_attempt.student
    if student is None:
        return False

    # Only sync when attempt is submitted or graded
    if assessment_attempt.status not in (
        AssessmentAttempt.STATUS_SUBMITTED,
        AssessmentAttempt.STATUS_GRADED,
    ):
        return False

    try:
        return _apply_assessment_sync(student, assignment, assessment_attempt)
    except Exception:
        logger.exception(
            "sync_assessment_submission failed assignment_id=%s attempt_id=%s",
            assignment.pk,
            assessment_attempt.pk,
        )
        return False


def _apply_assessment_sync(student, assignment: Assignment, assessment_attempt) -> bool:
    """
    Auto-grade assessment homework. Once the assessment engine finishes grading
    (status GRADED with a result), the class Submission goes straight to REVIEWED with an
    automatic grade = result.percent (out of 100) — it never enters the manual queue.
    While grading is still pending (SUBMITTED), record an interim submission; the assignment
    is auto-graded so it stays out of "Needs grading" regardless.
    """
    from django.db import IntegrityError

    from assessments.models import AssessmentAttempt

    with transaction.atomic():
        row = (
            Submission.objects.select_for_update()
            .filter(assignment=assignment, student=student)
            .first()
        )
        if row is None:
            try:
                row = Submission.objects.create(assignment=assignment, student=student)
            except IntegrityError:
                row = Submission.objects.select_for_update().get(
                    assignment=assignment, student=student
                )

        s = Submission.objects.select_for_update().get(pk=row.pk)

        existing_review = SubmissionReview.objects.filter(submission=s).first()
        manual_review = existing_review is not None and not existing_review.is_auto
        if s.status == Submission.STATUS_REVIEWED and manual_review:
            return False

        result = getattr(assessment_attempt, "result", None)
        graded = assessment_attempt.status == AssessmentAttempt.STATUS_GRADED
        percent = (
            float(result.percent)
            if (graded and result is not None and result.percent is not None)
            else None
        )

        if percent is not None:
            # Skip if already auto-graded with the same score.
            if (
                s.status == Submission.STATUS_REVIEWED
                and existing_review is not None
                and existing_review.is_auto
                and existing_review.grade is not None
                and float(existing_review.grade) == percent
            ):
                return False
            s.revision += 1
            _auto_grade(s, assignment, percent, 100, "assessment_graded", s.revision)
            s.save()
            return True

        # Grading still pending → interim submitted (only from editable states).
        if s.status in (Submission.STATUS_DRAFT, Submission.STATUS_RETURNED):
            s.revision += 1
            rev = s.revision
            prev_status = s.status
            s.mark_submitted()
            audit_submission_event(
                s.pk, None, SubmissionAuditEvent.EVENT_STATUS_CHANGE,
                {"from": prev_status, "to": s.status, "source": "assessment_attempt_submitted",
                 "assessment_attempt_id": assessment_attempt.pk},
                submission_revision=rev,
            )
            s.save()
            return True
        return False
