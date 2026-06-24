from __future__ import annotations

"""
LMS authorization — **use these entry points and no ad‑hoc shortcuts**.

**LOCKED CONTRACT (regressions)**

* **Questions authoring** (``/api/exams/admin/…``): :func:`can_manage_questions` — students denied;
  all other authenticated roles see full querysets. Student portal pastpaper list uses
  :func:`filter_practice_tests_for_user` with :func:`visible_practice_test_platform_subjects_for_query`
  (students: no ``PracticeTest.subject`` filter — full published bank).

* **View** test content (portal / library): :func:`can_view_tests`. **Edit** test content:
  :func:`can_edit_tests`. Public/portal querysets use :func:`filter_practice_tests_for_user`
  (from :func:`visible_practice_test_platform_subjects_for_query`).

* **Composite shells** (mock exams, pastpaper packs): use :func:`can_edit_multi_subject_object`
  or :func:`can_assign_all_platform_subjects_in_mock` so every underlying platform subject is
  checked.

* **Domain permissions**: :func:`authorize` with ``subject=`` (platform vocabulary). Cookies /
  client headers are **never** authorization inputs.

* **Querysets**: :func:`filter_practice_tests_for_user` / :func:`filter_mock_exams_for_user`
  must stay equivalent to ABAC helpers; enable
  ``LMS_AUTHZ_CONSISTENCY_CHECKS`` in dev to detect drift.

1. **Permission + resource subject (platform string)**  
   ``authorize(user, "<perm>", subject="<MATH|READING_WRITING>")``  
   See ``constants.PERMISSIONS_REQUIRING_PLATFORM_SUBJECT``. **Teachers** pass
   ``platform_subject_for_user(user)`` (their domain mapped to platform). **Global**
   staff (``admin``, ``test_admin``, ``super_admin``) bypass subject alignment inside
   ``authorize`` once the codename and a valid platform ``subject=`` are present; for
   *actor* checks that must compile for both teachers and globals, use
   ``actor_subject_probe_for_domain_perm(user)``.

2. **Database access (domain string)**  
   ``has_global_subject_access`` / ``has_access_for_classroom`` / ``student_has_any_subject_grant``  
   — always pass ``math`` / ``english`` (``constants.DOMAIN_*``), never platform strings.

3. **Converting** platform ↔ domain at boundaries — **only** ``access.subject_mapping``.

4. **PracticeTest visibility vs editing** — use ``can_view_tests`` / ``can_edit_tests`` /
   ``can_access_practice_test`` / ``access_level_for_practice_test`` so querysets and
   ``has_permission`` stay aligned. Client cookies are never inputs to these functions.
"""

from functools import lru_cache
from typing import FrozenSet, Literal, Optional

import logging

from django.apps import apps
from django.conf import settings
from django.db.models import Q

from . import constants
from .exceptions import AccessConsistencyDrift, SubjectContractViolation
from .subject_mapping import (
    domain_subject_to_platform,
    platform_subject_to_domain,
    validate_authorize_subject,
    validate_domain_subject_arg,
)

logger = logging.getLogger("access.authorize")
integrity_logger = logging.getLogger("access.data_integrity")

# DB / imports may still store pre-unification role strings; map to canonical roles only.
_LEGACY_ROLE_ALIASES: dict[str, str] = {
    "math_teacher": constants.ROLE_TEACHER,
    "english_teacher": constants.ROLE_TEACHER,
    "math_admin": constants.ROLE_ADMIN,
    "english_admin": constants.ROLE_ADMIN,
}


def _authorize_log_denial(reason: str, **ctx: object) -> None:
    """Structured denial log (INFO) for ops — tune logger level in production if noisy."""
    parts = " ".join(f"{k}={v!r}" for k, v in sorted(ctx.items()) if v is not None)
    logger.info("access.authorize denied: %s %s", reason, parts)


@lru_cache(maxsize=1)
def _role_permissions_map() -> dict[str, FrozenSet[str]]:
    return {
        constants.ROLE_SUPER_ADMIN: frozenset({constants.WILDCARD}),
        constants.ROLE_ADMIN: frozenset(
            {
                constants.PERM_VIEW_DASHBOARD,
                constants.PERM_MANAGE_USERS,
                constants.PERM_ASSIGN_ACCESS,
                constants.PERM_CREATE_CLASSROOM,
                constants.PERM_MANAGE_TESTS,
                constants.PERM_SUBMIT_TEST,
            }
        ),
        constants.ROLE_TEACHER: frozenset(
            {
                constants.PERM_VIEW_DASHBOARD,
                constants.PERM_ASSIGN_ACCESS,
                constants.PERM_CREATE_CLASSROOM,
                constants.PERM_MANAGE_TESTS,
                constants.PERM_SUBMIT_TEST,
            }
        ),
        constants.ROLE_TEST_ADMIN: frozenset(
            {
                constants.PERM_VIEW_DASHBOARD,
                constants.PERM_MANAGE_TESTS,
                # No PERM_ASSIGN_ACCESS: library authors configure sets on questions.*;
                # assignment into classrooms stays with teachers/class admins via admin subdomain.
                constants.PERM_SUBMIT_TEST,
            }
        ),
        constants.ROLE_STUDENT: frozenset({constants.PERM_SUBMIT_TEST}),
    }


def role_permissions_matrix() -> dict[str, FrozenSet[str]]:
    """
    One source of truth for role → permission codenames.

    Notes:
    - This is **role-level** policy (RBAC). ABAC subject rules are enforced by `authorize(...)`.
    - Callers should treat this mapping as read-only.
    - Teachers keep ``PERM_MANAGE_TESTS`` for practice/midterm editing; **assessment catalogue**
      writes use ``CanAuthorAssessmentContent`` (global staff only).
    - ``ROLE_TEST_ADMIN`` omits ``PERM_ASSIGN_ACCESS`` so authoring does not implicitly include
      assigning assessment homework — use classroom teachers on the admin subdomain for that flow.
    """
    return _role_permissions_map()


def normalized_role(user) -> str:
    if not user or not getattr(user, "is_authenticated", False):
        return constants.ROLE_STUDENT
    raw = getattr(user, "role", None)
    if not isinstance(raw, str) or not raw.strip():
        return constants.ROLE_STUDENT
    v = raw.strip().lower()
    if v in constants.CANONICAL_ROLES:
        return v
    if v in _LEGACY_ROLE_ALIASES:
        return _LEGACY_ROLE_ALIASES[v]
    return constants.ROLE_STUDENT


def can_manage_questions(user) -> bool:
    """
    Questions authoring API (``/api/exams/admin/...``): admins and teachers.

    Authoring rights extended to teachers so they can prepare their own
    assessments, mock exams, and practice tests for their classrooms.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    if is_global_scope_staff(user):
        return True
    return normalized_role(user) == constants.ROLE_TEACHER


def bulk_assign_request_platform_subjects(data: object) -> frozenset[str]:
    """
    Collect all platform subjects (MATH / READING_WRITING) touched by a bulk_assign payload.

    Used so ``authorize(PERM_ASSIGN_ACCESS, subject=...)`` can be evaluated per subject
    at the permission gate (fail closed; no silent cross-subject entry).
    """
    if not isinstance(data, dict):
        return frozenset()

    def _ints(seq):
        out: list[int] = []
        for x in seq or []:
            try:
                out.append(int(x))
            except (TypeError, ValueError):
                continue
        return out

    from exams.models import PracticeTest

    subjects: set[str] = set()
    for pk in _ints(data.get("practice_test_ids")):
        sub = (
            PracticeTest.objects.filter(pk=pk, mock_exam__isnull=True)
            .values_list("subject", flat=True)
            .first()
        )
        if sub:
            subjects.add(str(sub))

    exam_ids = _ints(data.get("exam_ids"))
    if exam_ids:
        assignment_type = data.get("assignment_type", "FULL")
        subject_map = {
            "MATH": (["MATH"], ["READING_WRITING"]),
            "ENGLISH": (["READING_WRITING"], ["MATH"]),
            "FULL": (["MATH", "READING_WRITING"], []),
        }
        to_add_subjects, _ = subject_map.get(assignment_type, (["MATH", "READING_WRITING"], []))
        if to_add_subjects:
            qs = PracticeTest.objects.filter(mock_exam_id__in=exam_ids, subject__in=to_add_subjects)
            form_type = data.get("form_type")
            if form_type:
                qs = qs.filter(form_type=form_type)
            subjects.update(qs.values_list("subject", flat=True))

    return frozenset(s for s in subjects if s)


def is_global_scope_staff(user) -> bool:
    """True for Django superuser and roles admin / test_admin / super_admin (no single subject scope)."""
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    r = normalized_role(user)
    return r in (
        constants.ROLE_SUPER_ADMIN,
        constants.ROLE_ADMIN,
        constants.ROLE_TEST_ADMIN,
    )


def user_domain_subject(user) -> Optional[str]:
    """
    Domain subject (``math`` / ``english``) **only for teachers**.

    ``None`` for global roles (admin, test_admin, super_admin), Django superuser, and students
    without a subject field — **do not** assume all staff have a domain here.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return None
    if is_global_scope_staff(user):
        return None
    if normalized_role(user) != constants.ROLE_TEACHER:
        return None
    raw = getattr(user, "subject", None)
    if isinstance(raw, str) and raw.strip().lower() in constants.ALL_DOMAIN_SUBJECTS:
        return raw.strip().lower()
    return None


def platform_subject_for_user(user) -> Optional[str]:
    """
    Platform subject for **teachers** only (``MATH`` / ``READING_WRITING``).

    ``None`` for global staff, superuser, and non-teachers — use
    :func:`actor_subject_probe_for_domain_perm` when passing ``subject=`` into :func:`authorize`
    for permission checks that must work for both teachers and global staff.
    """
    return domain_subject_to_platform(user_domain_subject(user))


def actor_subject_probe_for_domain_perm(user) -> Optional[str]:
    """
    Platform string to pass as ``authorize(..., subject=…)`` for *actor* permission checks.

    * **Global staff** — any valid platform label (subject alignment is bypassed in
      :func:`authorize`); we use ``MATH`` as a stable probe.
    * **Teacher** — that user's platform subject, or ``None`` if misconfigured.
    """
    if is_global_scope_staff(user):
        return constants.SUBJECT_MATH_PLATFORM
    return platform_subject_for_user(user)


def _user_access_model():
    return apps.get_model("access", "UserAccess")


def has_global_subject_access(user, domain_subject: str) -> bool:
    """
    **When to use:** decide if the user may act *across the whole domain* (``math`` /
    ``english``) using only **global** ``UserAccess`` rows (``classroom_id`` is NULL).

    **Not for:** classroom-scoped checks (use ``has_access_for_classroom``) or “any row”
    student eligibility (use ``student_has_any_subject_grant``).

    **Parameters:** ``domain_subject`` is always ``constants.DOMAIN_MATH`` or
    ``constants.DOMAIN_ENGLISH`` — never ``MATH`` / ``READING_WRITING``.

    **Teacher:** ``user.subject`` must match ``domain_subject`` and a matching ``UserAccess`` row exists.

    **Admin / test_admin:** global — returns ``True`` without a ``UserAccess`` self-row.

    Raises ``SubjectContractViolation`` if a platform subject string is passed by mistake.
    """
    validate_domain_subject_arg("has_global_subject_access", domain_subject)
    if domain_subject not in constants.ALL_DOMAIN_SUBJECTS:
        return False
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False) or normalized_role(user) == constants.ROLE_SUPER_ADMIN:
        return True

    role = normalized_role(user)
    UserAccess = _user_access_model()

    if role in (constants.ROLE_ADMIN, constants.ROLE_TEST_ADMIN):
        return True

    if role == constants.ROLE_TEACHER:
        if user_domain_subject(user) != domain_subject:
            return False
        return UserAccess.objects.filter(
            user_id=user.pk,
            subject=domain_subject,
            classroom_id__isnull=True,
        ).exists()

    if role == constants.ROLE_STUDENT:
        return UserAccess.objects.filter(
            user_id=user.pk,
            subject=domain_subject,
            classroom_id__isnull=True,
        ).exists()

    return False


def has_access_for_classroom(user, domain_subject: str, classroom_id: int) -> bool:
    """
    **When to use:** the resource is tied to **one classroom id** (grant flow, class-scoped
    admin). True if the user has a **global** grant in ``domain_subject`` *or* a row for
    that ``classroom_id`` (same domain).

    **Not for:** platform-wide permission checks — use ``authorize`` + platform subject.

    **Parameters:** ``domain_subject`` is ``DOMAIN_MATH`` / ``DOMAIN_ENGLISH`` only.

    Raises ``SubjectContractViolation`` if a platform subject string is passed by mistake.
    """
    validate_domain_subject_arg("has_access_for_classroom", domain_subject)
    if domain_subject not in constants.ALL_DOMAIN_SUBJECTS:
        return False
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False) or normalized_role(user) == constants.ROLE_SUPER_ADMIN:
        return True

    role = normalized_role(user)
    UserAccess = _user_access_model()
    cid = int(classroom_id)

    if role in (constants.ROLE_ADMIN, constants.ROLE_TEST_ADMIN):
        return True

    if role == constants.ROLE_STUDENT:
        return UserAccess.objects.filter(user_id=user.pk, subject=domain_subject).filter(
            Q(classroom_id__isnull=True) | Q(classroom_id=cid)
        ).exists()

    if role == constants.ROLE_TEACHER:
        if user_domain_subject(user) != domain_subject:
            return False
        return UserAccess.objects.filter(user_id=user.pk, subject=domain_subject).filter(
            Q(classroom_id__isnull=True) | Q(classroom_id=cid)
        ).exists()

    return False


def student_has_any_subject_grant(user, domain_subject: str) -> bool:
    """
    **When to use:** **students only** — e.g. bulk-assign eligibility (“can this student
    receive content tagged with this domain?”). True if **any** ``UserAccess`` row exists
    for ``domain_subject`` (global **or** classroom-specific).

    **Not for:** ``authorize()`` (students use ``has_global_subject_access`` there so
    classroom-only enrollment is not treated as full-subject platform access).

    **Not for:** staff — returns False for non-students.

    Raises ``SubjectContractViolation`` if a platform subject string is passed by mistake.
    """
    validate_domain_subject_arg("student_has_any_subject_grant", domain_subject)
    if domain_subject not in constants.ALL_DOMAIN_SUBJECTS:
        return False
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if normalized_role(user) != constants.ROLE_STUDENT:
        return False
    return _user_access_model().objects.filter(user_id=user.pk, subject=domain_subject).exists()


def get_effective_permission_codenames(user) -> FrozenSet[str]:
    if not user or not getattr(user, "is_authenticated", False):
        return frozenset()
    if getattr(user, "is_superuser", False):
        return frozenset({constants.WILDCARD})

    UserPermission = apps.get_model("access", "UserPermission")
    role = normalized_role(user)
    granted: set[str] = set(_role_permissions_map().get(role, frozenset({constants.PERM_SUBMIT_TEST})))

    overrides = UserPermission.objects.filter(user_id=user.pk).select_related("permission")
    for ov in overrides:
        if ov.granted:
            if (
                role == constants.ROLE_STUDENT
                and ov.permission.codename in constants.PERMISSIONS_STUDENT_OVERRIDE_DENIED
            ):
                continue
            granted.add(ov.permission.codename)
        else:
            granted.discard(ov.permission.codename)

    if constants.WILDCARD in granted:
        return frozenset({constants.WILDCARD})
    return frozenset(granted)


def can_edit_tests(user, platform_subject: str) -> bool:
    """
    **Edit** authoring (questions, shells, destructive ops): ``manage_tests`` / ``PERM_EDIT_TESTS`` only.

    **Global** staff (admin / test_admin / super_admin): no resource-subject alignment — edit is
    allowed iff the user has ``manage_tests`` (wildcard included). **Teachers** use ``authorize``.

    Authorization is **never** derived from client cookies or headers — only ``User`` + DB permissions.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if not isinstance(platform_subject, str) or not platform_subject.strip():
        return False
    platform_subject = platform_subject.strip()
    perms = get_effective_permission_codenames(user)
    if constants.WILDCARD in perms:
        return True
    if normalized_role(user) == constants.ROLE_STUDENT:
        return False
    if is_global_scope_staff(user):
        # Use authorize() so test_admin special-cases and subject contract are consistent.
        return authorize(user, constants.PERM_EDIT_TESTS, subject=platform_subject)
    return authorize(user, constants.PERM_EDIT_TESTS, subject=platform_subject)


def can_view_tests(user, platform_subject: str) -> bool:
    """
    **View** test library rows (list/retrieve): edit **or** ``assign_access`` in the same platform subject.

    **Global** staff: library view does **not** depend on ``platform_subject`` (role-global RBAC);
    requires ``manage_tests`` or ``assign_access``. **Teachers** are scoped to their domain subject.

    Do not use ``assign_access`` alone to imply edit — use :func:`can_edit_tests`.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if not isinstance(platform_subject, str) or not platform_subject.strip():
        return False
    platform_subject = platform_subject.strip()
    perms = get_effective_permission_codenames(user)
    if constants.WILDCARD in perms:
        return True
    if normalized_role(user) == constants.ROLE_STUDENT:
        return False
    if is_global_scope_staff(user):
        return constants.PERM_MANAGE_TESTS in perms or constants.PERM_ASSIGN_ACCESS in perms
    if can_edit_tests(user, platform_subject):
        return True
    return authorize(user, constants.PERM_ASSIGN_ACCESS, subject=platform_subject)


def can_assign_tests(user, platform_subject: str) -> bool:
    """
    **Assign** tests/sets into classrooms (homework).

    Semantics:
    - teachers: must have subject-scoped ``assign_access`` for their platform subject
    - global staff: must have ``assign_access`` (or wildcard); manage_tests alone is not enough
    """
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if not isinstance(platform_subject, str) or not platform_subject.strip():
        return False
    platform_subject = platform_subject.strip()
    perms = get_effective_permission_codenames(user)
    if constants.WILDCARD in perms:
        return True
    if normalized_role(user) == constants.ROLE_STUDENT:
        return False
    # Use authorize so subject contract + role-specific rules stay centralized.
    return authorize(user, constants.PERM_ASSIGN_ACCESS, subject=platform_subject)


def access_level_for_practice_test(user, practice_test: object) -> Literal["none", "view", "edit"]:
    """
    Single source of truth for “may this user see this PracticeTest row?” vs edit.

    Mirrors queryset rules: invalid ``PracticeTest.subject`` → ``none`` and a data-integrity log.
    """
    subj = getattr(practice_test, "subject", None)
    if not isinstance(subj, str) or not subj.strip():
        _log_invalid_practice_test_subject(practice_test)
        return "none"
    subj = subj.strip()
    if subj not in (constants.SUBJECT_MATH_PLATFORM, constants.SUBJECT_ENGLISH_PLATFORM):
        _log_invalid_practice_test_subject(practice_test)
        return "none"
    if normalized_role(user) == constants.ROLE_STUDENT:
        return "none"
    if can_edit_tests(user, subj):
        return "edit"
    if can_view_tests(user, subj):
        return "view"
    return "none"


def can_access_practice_test(user, practice_test: object) -> bool:
    """True if the user may list/retrieve this row (view or edit)."""
    return access_level_for_practice_test(user, practice_test) != "none"


def collect_platform_subjects_from_mock_exam(exam) -> list[str]:
    """All platform subjects represented on a timed mock (sections + midterm metadata)."""
    from exams.models import MockExam

    if getattr(exam, "kind", None) == MockExam.KIND_MIDTERM:
        sub = getattr(exam, "midterm_subject", None) or constants.SUBJECT_ENGLISH_PLATFORM
        return [sub] if sub else []
    return list(
        {t.subject for t in exam.tests.all() if getattr(t, "subject", None)}
    )


def can_edit_multi_subject_object(user, obj) -> bool:
    """
    True iff the user may **edit** every platform subject present on a composite object
    (``MockExam``). Single entry point for mocks — do not duplicate ``can_edit_tests``
    loops in view code.
    """
    from exams.models import MockExam

    if isinstance(obj, MockExam):
        subs = collect_platform_subjects_from_mock_exam(obj)
    else:
        raise TypeError(f"can_edit_multi_subject_object: unsupported type {type(obj)!r}")

    perms = get_effective_permission_codenames(user)
    if constants.WILDCARD in perms:
        return True
    if not subs:
        if is_global_scope_staff(user):
            return constants.PERM_MANAGE_TESTS in perms
        plat = platform_subject_for_user(user)
        return bool(plat and can_edit_tests(user, plat))
    return all(can_edit_tests(user, s) for s in subs)


def can_assign_all_platform_subjects_in_mock(user, exam) -> bool:
    """``assign_users`` on a mock: require ``assign_access`` on every section subject."""
    subs = collect_platform_subjects_from_mock_exam(exam)
    if not subs:
        return False
    return all(authorize(user, constants.PERM_ASSIGN_ACCESS, subject=s) for s in subs)


def visible_practice_test_platform_subjects_for_query(user) -> Optional[frozenset[str]]:
    """
    Platform subject(s) that may appear on **PracticeTest** rows visible to this user in SQL.

    * ``None`` — no ``PracticeTest.subject`` filter (wildcard, or **global** staff: ``user.subject`` is
      NULL; SQL must not try to match domain subject on content rows).
    * ``frozenset()`` — user may not see any tests (queryset should be empty).
    * ``frozenset({ "MATH" })`` etc. — **teacher**: one platform subject.

    **Single source of truth** with :func:`can_view_tests` (global staff: unfiltered querysets when
    they have effective permissions).

    **Anonymous / unauthenticated** callers (public ``GET /api/exams/``): ``None`` — no subject
    filter on standalone practice rows.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return None
    # Students: full published pastpaper bank (Math + R&W). Before ``perms`` empty-check so a
    # misconfigured permission row cannot hide the entire library.
    if normalized_role(user) == constants.ROLE_STUDENT:
        return None
    perms = get_effective_permission_codenames(user)
    if not perms:
        return frozenset()
    if constants.WILDCARD in perms:
        return None
    # Global roles never carry user.subject; SQL must not filter the library by subject.
    if is_global_scope_staff(user):
        if not can_view_tests(user, constants.SUBJECT_MATH_PLATFORM):
            return frozenset()
        return None
    plat = platform_subject_for_user(user)
    if not plat:
        return frozenset()
    if not can_view_tests(user, plat):
        return frozenset()
    return frozenset([plat])


def _log_invalid_practice_test_subject(practice_test: object) -> None:
    pk = getattr(practice_test, "pk", None)
    subj = getattr(practice_test, "subject", None)
    integrity_logger.error(
        "invalid PracticeTest.subject: id=%r subject=%r (expected MATH or READING_WRITING)",
        pk,
        subj,
    )


def debug_log_queryset_vs_can_view_tests(user, practice_test: object, filtered_queryset) -> None:
    """
    When ``settings.LMS_AUTHZ_CONSISTENCY_CHECKS`` is True, log if SQL visibility disagrees
    with :func:`can_view_tests` for this row (catches queryset / authorize drift).

    If ``settings.LMS_AUTHZ_RAISE_ON_CONSISTENCY_DRIFT`` is True (default: same as ``DEBUG``),
    raises :exc:`AccessConsistencyDrift`.
    """
    if not getattr(settings, "LMS_AUTHZ_CONSISTENCY_CHECKS", False):
        return
    subj = getattr(practice_test, "subject", None)
    if not isinstance(subj, str):
        return
    try:
        in_qs = filtered_queryset.filter(pk=getattr(practice_test, "pk", None)).exists()
    except Exception:
        return
    can_see = can_view_tests(user, subj)
    if in_qs != can_see:
        msg = (
            f"access consistency drift: user_id={getattr(user, 'pk', None)} "
            f"test_id={getattr(practice_test, 'pk', None)} subject={subj!r} "
            f"in_queryset={in_qs} can_view_tests={can_see}"
        )
        logger.warning(msg)
        if getattr(settings, "LMS_AUTHZ_RAISE_ON_CONSISTENCY_DRIFT", False):
            raise AccessConsistencyDrift(msg)


def is_lms_staff_user(user) -> bool:
    perms = get_effective_permission_codenames(user)
    if not perms:
        return False
    if constants.WILDCARD in perms:
        return True
    return constants.PERM_MANAGE_USERS in perms or constants.PERM_VIEW_DASHBOARD in perms


def authorize(user, permission_codename: str, *, subject: Optional[str] = None) -> bool:
    """
    **The** permission API for views/policies: codename + optional **platform** ``subject``.

    * ``subject`` = ``constants.SUBJECT_MATH_PLATFORM`` or ``constants.SUBJECT_ENGLISH_PLATFORM``
      whenever ``permission_codename`` ∈ ``PERMISSIONS_REQUIRING_PLATFORM_SUBJECT``.
    * Do **not** pass ``math`` / ``english`` here — use ``subject_mapping.domain_subject_to_platform``.

    Exceptions where ``subject`` may be omitted (still in the set above):

    * ``super_admin`` / Django superuser.

    Permissions **outside** ``PERMISSIONS_REQUIRING_PLATFORM_SUBJECT`` (e.g.
    ``view_dashboard``, ``submit_test``): ignore ``subject``; pass ``None``.

    **Misuse guardrails:** If ``subject`` is provided for a domain-scoped permission, it must
    be a valid **platform** string; otherwise ``SubjectContractViolation`` is raised.
    If ``subject`` is omitted when required, the call returns ``False`` (deny) and logs an
    INFO line via ``access.authorize`` so missing wiring is visible in logs.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return False

    perms = get_effective_permission_codenames(user)
    if constants.WILDCARD in perms:
        return True

    role = normalized_role(user)
    # Role implies manage_tests for org-wide testers; DB overrides may strip the codename.
    has_codename = permission_codename in perms
    if (
        not has_codename
        and role == constants.ROLE_TEST_ADMIN
        and permission_codename == constants.PERM_MANAGE_TESTS
    ):
        has_codename = True
    if not has_codename:
        _authorize_log_denial(
            "missing_permission_codename",
            perm=permission_codename,
            user_id=getattr(user, "pk", None),
            role=role,
        )
        return False

    if permission_codename not in constants.PERMISSIONS_REQUIRING_PLATFORM_SUBJECT:
        return True
    is_privileged = getattr(user, "is_superuser", False) or role == constants.ROLE_SUPER_ADMIN

    if subject is None:
        if is_privileged:
            return True
        _authorize_log_denial(
            "missing_subject_argument",
            perm=permission_codename,
            user_id=getattr(user, "pk", None),
            role=role,
        )
        if getattr(settings, "LMS_AUTHZ_RAISE_ON_MISSING_SUBJECT", False):
            raise SubjectContractViolation(
                f"authorize() requires subject= for permission {permission_codename!r} "
                f"(use constants.SUBJECT_*_PLATFORM or platform_subject_for_user(user))."
            )
        return False

    validate_authorize_subject(subject)
    required = platform_subject_to_domain(subject)
    if required not in constants.ALL_DOMAIN_SUBJECTS:
        # Defensive: validate_authorize_subject should already have enforced platform vocabulary.
        raise SubjectContractViolation(
            f"authorize() received unknown platform subject {subject!r}."
        )

    if is_privileged:
        return True

    # admin / test_admin: global scope — no user.subject alignment for resource subject.
    if role in (constants.ROLE_ADMIN, constants.ROLE_TEST_ADMIN):
        return True

    if role == constants.ROLE_TEACHER:
        udom = user_domain_subject(user)
        if udom != required:
            _authorize_log_denial(
                "actor_subject_mismatch",
                perm=permission_codename,
                user_id=getattr(user, "pk", None),
                role=role,
                required_domain=required,
                user_domain=udom,
            )
            return False
        if not has_global_subject_access(user, required):
            _authorize_log_denial(
                "no_global_useraccess_row",
                perm=permission_codename,
                user_id=getattr(user, "pk", None),
                role=role,
                domain=required,
            )
            return False
        return True

    if role == constants.ROLE_STUDENT:
        if not has_global_subject_access(user, required):
            _authorize_log_denial(
                "student_no_subject_grant",
                perm=permission_codename,
                user_id=getattr(user, "pk", None),
                domain=required,
            )
            return False
        return True

    _authorize_log_denial(
        "unsupported_role",
        perm=permission_codename,
        user_id=getattr(user, "pk", None),
        role=role,
    )
    return False


def can_browse_standalone_practice_library(user) -> bool:
    """Staff library browser: same visibility as :func:`can_view_tests` (probe subject for globals)."""
    perms = get_effective_permission_codenames(user)
    if constants.WILDCARD in perms:
        return True
    plat = actor_subject_probe_for_domain_perm(user)
    if not plat:
        return False
    return can_view_tests(user, plat)


def _debug_log_test_library_filter(
    name: str,
    user,
    queryset_before,
    queryset_after,
) -> None:
    if not getattr(settings, "LMS_AUTHZ_DEBUG_FILTERS", False):
        return
    try:
        n_before = queryset_before.count()
    except Exception as exc:
        n_before = f"<err:{exc}>"
    try:
        n_after = queryset_after.count()
    except Exception as exc:
        n_after = f"<err:{exc}>"
    logger.info(
        "access.test_library_filter %s user_id=%s role=%r subject=%r count_before=%s count_after=%s",
        name,
        getattr(user, "pk", None),
        getattr(user, "role", None),
        getattr(user, "subject", None),
        n_before,
        n_after,
    )


def filter_practice_tests_for_user(user, queryset):
    """
    SQL filter **derived only** from :func:`visible_practice_test_platform_subjects_for_query`
    (which calls :func:`can_view_tests`). No parallel role / subject branching here.
    """
    subjs = visible_practice_test_platform_subjects_for_query(user)
    if subjs is not None and not subjs:
        out = queryset.none()
        _debug_log_test_library_filter("filter_practice_tests_for_user", user, queryset, out)
        return out
    if subjs is None:
        out = queryset
        _debug_log_test_library_filter("filter_practice_tests_for_user", user, queryset, out)
        return out
    out = queryset.filter(subject__in=subjs)
    _debug_log_test_library_filter("filter_practice_tests_for_user", user, queryset, out)
    return out


def filter_mock_exams_for_user(user, queryset):
    from django.db.models import Count

    from exams.models import PracticeTest

    subjs = visible_practice_test_platform_subjects_for_query(user)
    if subjs is not None and not subjs:
        out = queryset.none()
        _debug_log_test_library_filter("filter_mock_exams_for_user", user, queryset, out)
        return out

    if subjs is None:
        _debug_log_test_library_filter("filter_mock_exams_for_user", user, queryset, queryset)
        return queryset

    visible_tests = filter_practice_tests_for_user(user, PracticeTest.objects.all())
    with_tests = queryset.filter(tests__in=visible_tests)
    empty_shells = queryset.annotate(_tc=Count("tests")).filter(_tc=0)
    out = (with_tests | empty_shells).distinct()
    _debug_log_test_library_filter("filter_mock_exams_for_user", user, queryset, out)
    return out


def user_can_assign_as_class_teacher(user) -> bool:
    probe = actor_subject_probe_for_domain_perm(user)
    if not probe:
        return False
    return authorize(user, constants.PERM_MANAGE_USERS, subject=probe) or authorize(
        user, constants.PERM_CREATE_CLASSROOM, subject=probe
    )


def staff_must_have_subject(user) -> bool:
    """Only **teachers** must carry a domain ``subject``; global roles do not."""
    return normalized_role(user) == constants.ROLE_TEACHER
