"""
enforcement.py — write-through from engine grants to the *currently active*
legacy enforcement signal.

Why this exists: a ``ResourceAccessGrant`` row alone is invisible to students,
because no student-facing view reads it in production (``ACCESS_ENGINE_READ`` is
off and ``VisibilityService`` is wired into nothing). Student access to tests /
packs / mocks is still gated by the legacy ``assigned_users`` M2Ms
(``exams/views.py`` — e.g. ``base.filter(assigned_users=user)``). So every engine
grant must **also** write that legacy signal, in the *same transaction* as the
grant, and the result must be **verified** before success is reported.

This writes the same ``assigned_users`` signal the student read path consults:

* ``practice_test`` -> ``PracticeTest.assigned_users``
* ``mock_exam``     -> ``MockExam.assigned_users`` + every section
  ``PracticeTest.assigned_users`` + ``PortalMockExam.assigned_users``

We deliberately do **not** create a global ``UserAccess`` subject grant here: the
student read gate (list + attempt creation) is ``assigned_users`` alone, so a
resource grant must confer *resource* access only — never widen the student to a
whole subject (which would, e.g., make "Pack X + Math" leak into other Math
content). Subject access is granted explicitly via the SUBJECT scope, which keeps
its own ``UserAccess`` write-through in :class:`AssignmentService`.

Pack types are expanded to their section ``practice_test`` targets *before*
reaching here (see :func:`access.resources.expand_subject_targets`), which is how
Math / Reading / Both is enforced — only the chosen sections are written.

All operations are idempotent (M2M ``add`` of existing members is a no-op;
``UserAccess`` via ``get_or_create``), so re-granting repairs any drifted state —
including students who already hold a grant row but were never added to
``assigned_users`` (the production bug this fixes).
"""

from __future__ import annotations

import logging
from typing import Iterable

from access import constants, resources
from access.services import normalized_role

logger = logging.getLogger("access.enforcement")


class AccessVerificationError(Exception):
    """
    Raised when, after writing grant + legacy enforcement, a student still cannot
    see the resource through the active read path. Forces a transaction rollback so
    the API never reports success without real, usable access.
    """


def _students(users: Iterable) -> list:
    return [u for u in users if normalized_role(u) == constants.ROLE_STUDENT]


# -- write-through ----------------------------------------------------------

def apply_resource(resource_type: str, resource_id: int, users: Iterable, *, actor=None) -> None:
    """
    Write the legacy enforcement signal for one already-expanded resource target.

    No-op for users that are not students (staff are governed by RBAC, not
    ``assigned_users``) and for resource types that carry no ``assigned_users``
    gate (``assessment_set`` is enforced via ``HomeworkAssignment``; ``module``
    has no student gate).
    """
    students = _students(users)
    if not students:
        return
    if resource_type == resources.RT_PRACTICE_TEST:
        _apply_practice_test(resource_id, students, actor)
    elif resource_type in (resources.RT_MOCK_EXAM, resources.RT_MIDTERM):
        # A midterm is a MockExam(kind=MIDTERM); identical student gate.
        _apply_mock_exam(resource_id, students, actor)
    else:
        logger.debug("enforcement: no legacy gate for resource_type=%s", resource_type)


def _apply_practice_test(pk: int, students: list, actor) -> None:
    from exams.models import PracticeTest

    pt = PracticeTest.objects.filter(pk=pk).first()
    if pt is None:
        return
    pt.assigned_users.add(*students)


def _apply_mock_exam(pk: int, students: list, actor) -> None:
    from exams.models import MockExam, PortalMockExam

    exam = MockExam.objects.filter(pk=pk).first()
    if exam is None:
        return
    exam.assigned_users.add(*students)
    for sec in exam.tests.all():
        sec.assigned_users.add(*students)
    portal, _ = PortalMockExam.objects.get_or_create(
        mock_exam=exam,
        defaults={"is_active": bool(getattr(exam, "is_published", True))},
    )
    portal.assigned_users.add(*students)


# -- verification (read-path truth) ----------------------------------------

def unverified_students(resource_type: str, resource_id: int, users: Iterable) -> list:
    """
    Return the students who still cannot see ``(resource_type, resource_id)`` via
    the active legacy read gate. Empty list means every student has usable access.
    Resource types with no legacy gate are treated as verified (nothing to check).
    """
    students = _students(users)
    if not students:
        return []
    student_ids = {u.pk for u in students}
    if resource_type == resources.RT_PRACTICE_TEST:
        from exams.models import PracticeTest

        ok = set(
            PracticeTest.objects.filter(
                pk=resource_id, assigned_users__in=student_ids
            ).values_list("assigned_users", flat=True)
        )
    elif resource_type in (resources.RT_MOCK_EXAM, resources.RT_MIDTERM):
        from exams.models import PortalMockExam

        ok = set(
            PortalMockExam.objects.filter(
                mock_exam_id=resource_id, assigned_users__in=student_ids
            ).values_list("assigned_users", flat=True)
        )
    else:
        return []
    return [u for u in students if u.pk not in ok]


def verify_targets(targets: Iterable, users: Iterable) -> None:
    """
    Verify every (target, student) pair is visible through the active read path.
    Raise :class:`AccessVerificationError` (rolling back the surrounding
    transaction) if any student is still locked out of any target.
    """
    failures: list[str] = []
    for rt, rid in targets:
        bad = unverified_students(rt, rid, users)
        if bad:
            ids = ", ".join(str(u.pk) for u in bad)
            failures.append(f"{rt}#{rid} (users: {ids})")
    if failures:
        raise AccessVerificationError(
            "Access was recorded but is not yet usable for: " + "; ".join(failures)
        )
