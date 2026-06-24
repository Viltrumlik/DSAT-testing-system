from __future__ import annotations

from dataclasses import dataclass

from .models import ClassroomMembership


@dataclass(frozen=True)
class ClassroomAuthz:
    is_class_admin: bool
    is_teacher_owner: bool


def classroom_authz_for_user(*, classroom, user) -> ClassroomAuthz:
    """
    Centralized classroom authorization signals.

    - is_class_admin: user has ADMIN membership in this classroom
    - is_teacher_owner: user is the classroom.teacher (ownership)
    """
    if not classroom or not user or not getattr(user, "is_authenticated", False):
        return ClassroomAuthz(is_class_admin=False, is_teacher_owner=False)

    is_admin = classroom.memberships.filter(user=user, role=ClassroomMembership.ROLE_ADMIN).exists()
    is_owner = bool(getattr(classroom, "teacher_id", None) and classroom.teacher_id == user.pk)
    return ClassroomAuthz(is_class_admin=is_admin, is_teacher_owner=is_owner)

