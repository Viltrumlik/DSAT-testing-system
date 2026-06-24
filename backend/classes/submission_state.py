"""
Strict submission status transitions for classroom homework.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from .models import Submission

Actor = Literal["student", "teacher", "system"]


def transition_student_submit() -> frozenset[str]:
    """Statuses from which a student may finalize submission (→ SUBMITTED)."""
    from .models import Submission

    return frozenset({Submission.STATUS_DRAFT, Submission.STATUS_RETURNED})


def transition_student_may_edit_files(status: str) -> bool:
    from .models import Submission

    return status in (Submission.STATUS_DRAFT, Submission.STATUS_RETURNED)


def student_may_edit_submission_before_deadline(submission: "Submission") -> bool:
    """SUBMITTED work can be changed until the assignment due time (if any)."""
    from django.utils import timezone

    from .models import Submission

    if submission.status != Submission.STATUS_SUBMITTED:
        return False
    due = submission.assignment.due_at
    if due is None:
        return True
    return timezone.now() <= due


def transition_teacher_may_grade(status: str) -> bool:
    from .models import Submission

    return status in (Submission.STATUS_SUBMITTED, Submission.STATUS_REVIEWED)


def transition_teacher_may_return(status: str) -> bool:
    from .models import Submission

    return status in (Submission.STATUS_SUBMITTED, Submission.STATUS_REVIEWED)


def assert_teacher_grade_allowed(submission: Submission) -> None:
    from rest_framework.exceptions import ValidationError

    if not transition_teacher_may_grade(submission.status):
        raise ValidationError(
            {"detail": f"Cannot grade submission in status {submission.status}."},
            code="invalid_transition",
        )


def assert_teacher_return_allowed(submission: Submission) -> None:
    from rest_framework.exceptions import ValidationError

    if not transition_teacher_may_return(submission.status):
        raise ValidationError(
            {"detail": f"Cannot return submission in status {submission.status}."},
            code="invalid_transition",
        )


def assert_student_edit_allowed(submission: Submission) -> None:
    from rest_framework.exceptions import ValidationError

    from .models import Submission

    if transition_student_may_edit_files(submission.status):
        return
    if submission.status == Submission.STATUS_SUBMITTED and student_may_edit_submission_before_deadline(submission):
        return
    raise ValidationError(
        {"detail": f"This submission is locked (status {submission.status})."},
        code="locked",
    )
