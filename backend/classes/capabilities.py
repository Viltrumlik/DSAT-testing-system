"""Classroom capability resolution — the single source of truth for who-can-do-what
inside one classroom. Mirrors the finalized TA capability matrix (BUSINESS-ARCHITECTURE §2)
and the frontend features/classroom/capabilities.ts.

Two layers (§0): a *global admin* (super_admin/admin/superuser) overrides everything;
otherwise capabilities derive from the ACTIVE ClassroomMembership.role. Never compare
role strings inline in views — call `classroom_capabilities()` / `can()` or the DRF classes
in classes/permissions.py that consume it.

Tiers: Owner-only · Teacher+Owner (manager) · TA+Teacher+Owner (staff) · Student.
TA owns recurring instructional work (content + assessment); Owner/Teacher own governance.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict

from .models import ClassroomMembership


def is_global_admin(user) -> bool:
    """Org-wide admins that bypass classroom-local role checks: super_admin / admin / Django
    superuser ONLY.

    Deliberately does NOT use ``user.is_admin``: that property is permission-based
    (``is_lms_staff_user``) and is True for ordinary teachers, which previously made every
    teacher a "global admin" — granting full capabilities (and membership) on *any* classroom
    via classroom_capabilities + IsClassMemberCap. Membership/ownership must be a real security
    boundary, so global-admin status is now strictly role-based.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return str(getattr(user, "role", "") or "").strip().lower() in ("super_admin", "admin")


@dataclass(frozen=True)
class Capabilities:
    is_member: bool
    is_staff: bool                 # TA + Teacher + Owner
    is_student: bool
    is_owner: bool
    # Instructional work — TA + Teacher + Owner
    can_manage_assignments: bool   # create / edit / publish / archive / unarchive
    can_grade: bool                # grade + return for revision
    can_take_attendance: bool
    can_post_announcement: bool
    can_view_class_analytics: bool
    can_recompute_ranking: bool
    # Governance — Teacher + Owner
    can_manage_class: bool         # edit settings, deactivate, join code
    can_delete_assignment: bool    # hard delete (TA archives instead)
    can_manage_roster: bool        # add / remove students
    can_configure_ranking: bool    # weights + leaderboard visibility
    # Owner only
    can_assign_ta: bool            # appoint / revoke TAs and teachers
    can_delete_class: bool
    role: str | None               # ADMIN/OWNER/TEACHER/TA/STUDENT or "GLOBAL_ADMIN"

    def as_dict(self) -> dict:
        return asdict(self)


def _make(*, is_member, is_staff, is_student, is_owner, is_manager) -> Capabilities:
    return Capabilities(
        is_member=is_member,
        is_staff=is_staff,
        is_student=is_student,
        is_owner=is_owner,
        can_manage_assignments=is_staff,
        can_grade=is_staff,
        can_take_attendance=is_staff,
        can_post_announcement=is_staff,
        can_view_class_analytics=is_staff,
        can_recompute_ranking=is_staff,
        can_manage_class=is_manager,
        can_delete_assignment=is_manager,
        can_manage_roster=is_manager,
        can_configure_ranking=is_manager,
        can_assign_ta=is_owner,
        can_delete_class=is_owner,
        role=None,
    )


_NONE = _make(is_member=False, is_staff=False, is_student=False, is_owner=False, is_manager=False)


def _membership_role(user, classroom) -> str | None:
    if not user or not getattr(user, "is_authenticated", False) or classroom is None:
        return None
    return (
        ClassroomMembership.objects.filter(classroom=classroom, user=user)
        .exclude(status=ClassroomMembership.STATUS_REMOVED)
        .values_list("role", flat=True)
        .first()
    )


def classroom_capabilities(user, classroom) -> Capabilities:
    """Resolve the viewer's capabilities for one classroom."""
    if is_global_admin(user):
        caps = _make(is_member=True, is_staff=True, is_student=False, is_owner=True, is_manager=True)
        return Capabilities(**{**caps.as_dict(), "role": "GLOBAL_ADMIN"})

    role = _membership_role(user, classroom)
    if role is None:
        return _NONE

    is_staff = role in ClassroomMembership.STAFF_ROLES
    is_manager = role in ClassroomMembership.MANAGER_ROLES
    is_owner = role in (ClassroomMembership.ROLE_OWNER, ClassroomMembership.ROLE_ADMIN)
    is_student = role == ClassroomMembership.ROLE_STUDENT
    caps = _make(is_member=True, is_staff=is_staff, is_student=is_student, is_owner=is_owner, is_manager=is_manager)
    return Capabilities(**{**caps.as_dict(), "role": role})


def can(user, classroom, capability: str) -> bool:
    """Convenience for legacy views: classroom_capabilities(...).<capability>."""
    return bool(getattr(classroom_capabilities(user, classroom), capability, False))
