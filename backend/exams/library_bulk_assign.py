"""
Server-side library bulk assign execution + structured outcome for history / UI.

Kept separate from ``views`` to keep HTTP thin and allow re-run from stored payloads.
"""

from __future__ import annotations

from typing import Any

from django.contrib.auth import get_user_model
from django.db import transaction

from access import constants as acc_const
from access.models import UserAccess
from access.services import authorize, normalized_role, student_has_any_subject_grant
from access.subject_mapping import platform_subject_to_domain

from .models import MockExam, PortalMockExam, PracticeTest

User = get_user_model()


def _ensure_global_grants_for_students(actor, users: list, platform_subject: str) -> int:
    """
    When an actor may assign library content for ``platform_subject``, ensure each student
    has a global domain grant (``UserAccess`` with ``classroom`` NULL). Without this, bulk
    assign would skip students who have not yet received Math/English access — even though
    the actor is explicitly granting them tests.
    """
    if not authorize(actor, acc_const.PERM_ASSIGN_ACCESS, subject=platform_subject):
        return 0
    dom = platform_subject_to_domain(platform_subject)
    if not dom:
        return 0
    created_n = 0
    for u in users:
        if normalized_role(u) != acc_const.ROLE_STUDENT:
            continue
        if student_has_any_subject_grant(u, dom):
            continue
        _grant, was_created = UserAccess.objects.get_or_create(
            user=u,
            subject=dom,
            classroom=None,
            defaults={"granted_by": actor},
        )
        if was_created:
            created_n += 1
        else:
            UserAccess.objects.filter(pk=_grant.pk).update(granted_by_id=actor.pk)
    return created_n


def _as_int_ids(seq: Any) -> list[int]:
    out: list[int] = []
    for x in seq or []:
        try:
            out.append(int(x))
        except (TypeError, ValueError):
            continue
    return out


def _allowed_students_for_platform_subject(users: list, platform_subject: str) -> list:
    dom = platform_subject_to_domain(platform_subject)
    if not dom:
        return []
    return [
        u
        for u in users
        if normalized_role(u) == acc_const.ROLE_STUDENT and student_has_any_subject_grant(u, dom)
    ]


def _skip_reason(user, subjects_touched: set[str]) -> str:
    role = normalized_role(user)
    if role != acc_const.ROLE_STUDENT:
        return "Not a student account"
    if not subjects_touched:
        return "No matching tests for this request"
    parts: list[str] = []
    for subj in sorted(subjects_touched):
        dom = platform_subject_to_domain(subj)
        if dom and not student_has_any_subject_grant(user, dom):
            label = "Math" if subj == "MATH" else "Reading & Writing"
            parts.append(f"No {label} access")
    if parts:
        return "; ".join(parts)
    return "No library access applied for this selection"


def execute_library_bulk_assign(
    *,
    actor,
    exam_ids: list[int],
    practice_test_ids: list[int],
    user_ids: list[int],
    assignment_type: str,
    form_type: str | None,
) -> dict[str, Any]:
    """
    Apply bulk library assignment. Runs in caller's transaction when used inside ``atomic()``.

    Returns API-shaped dict including ``skipped_users`` and ``subjects_touched``.
    """
    users = list(User.objects.filter(id__in=user_ids))
    added_count = 0
    removed_count = 0
    practice_tests_matched = 0
    exam_tests_matched = 0
    subject_grants_created = 0
    touched_student_ids: set[int] = set()
    subjects_touched: set[str] = set()
    # Subjects the actor was NOT permitted to assign — these silently skipped
    # before, producing zero-recipient "success". Surfaced in the result so the
    # admin UI can show a permission-denied warning instead of a fake success.
    permission_denied_subjects: set[str] = set()

    if practice_test_ids:
        pts = PracticeTest.objects.filter(pk__in=practice_test_ids, mock_exam__isnull=True)
        practice_tests_matched = pts.count()
        for pt in pts:
            subjects_touched.add(str(pt.subject))
            if authorize(actor, acc_const.PERM_ASSIGN_ACCESS, subject=pt.subject):
                subject_grants_created += _ensure_global_grants_for_students(actor, users, pt.subject)
                allowed = _allowed_students_for_platform_subject(users, pt.subject)
                if allowed:
                    pt.assigned_users.add(*allowed)
                    for u in allowed:
                        touched_student_ids.add(u.pk)
                    added_count += 1
            else:
                permission_denied_subjects.add(str(pt.subject))

    mock_ids_touched: set[int] = set()
    if exam_ids:
        subject_map = {
            "MATH": (["MATH"], ["READING_WRITING"]),
            "ENGLISH": (["READING_WRITING"], ["MATH"]),
            "FULL": (["MATH", "READING_WRITING"], []),
        }
        to_add_subjects, to_remove_subjects = subject_map.get(
            assignment_type, (["MATH", "READING_WRITING"], [])
        )

        add_filters: dict[str, Any] = {"mock_exam_id__in": exam_ids, "subject__in": to_add_subjects}
        if form_type:
            add_filters["form_type"] = form_type

        add_tests = PracticeTest.objects.filter(**add_filters)
        for pt in add_tests:
            exam_tests_matched += 1
            subjects_touched.add(str(pt.subject))
            if authorize(actor, acc_const.PERM_ASSIGN_ACCESS, subject=pt.subject):
                subject_grants_created += _ensure_global_grants_for_students(actor, users, pt.subject)
                allowed = _allowed_students_for_platform_subject(users, pt.subject)
                if allowed:
                    pt.assigned_users.add(*allowed)
                    for u in allowed:
                        touched_student_ids.add(u.pk)
                    added_count += 1
                if pt.mock_exam_id:
                    mock_ids_touched.add(pt.mock_exam_id)
            else:
                permission_denied_subjects.add(str(pt.subject))

        touched_users = [u for u in users if u.pk in touched_student_ids]
        for me in MockExam.objects.filter(pk__in=mock_ids_touched):
            if touched_users:
                me.assigned_users.add(*touched_users)
            portal, _ = PortalMockExam.objects.get_or_create(
                mock_exam=me,
                defaults={"is_active": bool(me.is_published)},
            )
            if touched_users:
                portal.assigned_users.add(*touched_users)

        if to_remove_subjects:
            remove_filters: dict[str, Any] = {"mock_exam_id__in": exam_ids, "subject__in": to_remove_subjects}
            if form_type:
                remove_filters["form_type"] = form_type
            remove_tests = PracticeTest.objects.filter(**remove_filters)
            for pt in remove_tests:
                subjects_touched.add(str(pt.subject))
                if authorize(actor, acc_const.PERM_ASSIGN_ACCESS, subject=pt.subject):
                    allowed = _allowed_students_for_platform_subject(users, pt.subject)
                    if allowed:
                        pt.assigned_users.remove(*allowed)
                        removed_count += 1

    skipped_users: list[dict[str, Any]] = []
    for u in users:
        if normalized_role(u) != acc_const.ROLE_STUDENT:
            continue
        if u.pk in touched_student_ids:
            continue
        skipped_users.append(
            {
                "user_id": u.pk,
                "username": getattr(u, "username", "") or "",
                "display_name": _display_name(u),
                "reason": _skip_reason(u, subjects_touched),
            }
        )

    student_requested = sum(1 for u in users if normalized_role(u) == acc_const.ROLE_STUDENT)
    students_granted = sum(1 for u in users if normalized_role(u) == acc_const.ROLE_STUDENT and u.pk in touched_student_ids)
    students_skipped_count = student_requested - students_granted

    # Did any target content actually match the request, independent of
    # permission? (e.g. practice_test_ids that were all timed-mock sections, or
    # exam filters that matched nothing.) Permission-denied matches still count
    # as "targets matched" so they resolve to no_recipients, not no_targets.
    targets_matched = (practice_tests_matched + exam_tests_matched) > 0
    no_targets = (bool(practice_test_ids) or bool(exam_ids)) and not targets_matched

    # Explicit, single source of truth for the admin UI so success can NEVER be
    # reported when zero student access rows were written.
    if no_targets:
        outcome = "no_targets"          # nothing matched — empty target
    elif students_granted == 0:
        outcome = "no_recipients"       # matched content but 0 students got access
    elif students_skipped_count > 0:
        outcome = "partial"             # some granted, some skipped
    else:
        outcome = "granted"             # everyone requested received access
    succeeded = outcome in ("granted", "partial")

    return {
        "status": "bulk_assigned",
        "outcome": outcome,
        "succeeded": succeeded,
        "permission_denied_subjects": sorted(permission_denied_subjects),
        "exams_count": len(exam_ids),
        "practice_tests_requested": len(practice_test_ids),
        "practice_tests_matched": practice_tests_matched,
        "exam_tests_matched": exam_tests_matched,
        "practice_tests_count": len(practice_test_ids),
        "tests_added": added_count,
        "tests_removed": removed_count,
        "users_count": len(users),
        "type": assignment_type,
        "skipped_users": skipped_users,
        "students_requested_count": student_requested,
        "students_granted_count": students_granted,
        "students_skipped_count": students_skipped_count,
        "subjects_touched": sorted(subjects_touched),
        "subject_grants_created": subject_grants_created,
    }


def _display_name(user) -> str:
    fn = (getattr(user, "first_name", None) or "").strip()
    ln = (getattr(user, "last_name", None) or "").strip()
    n = f"{fn} {ln}".strip()
    if n:
        return n
    u = (getattr(user, "username", None) or "").strip()
    if u:
        return u
    return f"User #{user.pk}"


def infer_dispatch_kind(exam_ids: list[int], practice_test_ids: list[int]) -> str:
    """Persisted ``BulkAssignmentDispatch.kind`` value."""
    if practice_test_ids and exam_ids:
        return "mixed"
    if practice_test_ids:
        return "pastpaper"
    return "timed_mock"


def subject_summary_from_subjects(subjects: list[str]) -> str:
    if not subjects:
        return ""
    labels = []
    for s in sorted(set(subjects)):
        if s == "MATH":
            labels.append("Math")
        elif s == "READING_WRITING":
            labels.append("Reading & Writing")
        else:
            labels.append(str(s))
    return ", ".join(labels)
