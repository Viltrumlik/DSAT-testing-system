from rest_framework.permissions import BasePermission

from .models import ClassroomMembership


class IsAdminUser(BasePermission):
    """
    App-level admin check: reuse user's `is_admin` convenience property.
    """

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and getattr(request.user, "is_admin", False))


class IsClassMember(BasePermission):
    """
    Require the current user to be a member of the classroom.
    Assumes view has `get_classroom()` method.
    """

    message = "You are not a member of this class."

    def has_permission(self, request, view):
        classroom = getattr(view, "get_classroom", lambda: None)()
        if classroom is None:
            return False
        return (
            classroom.memberships.filter(user=request.user)
            .exclude(status=ClassroomMembership.STATUS_REMOVED)
            .exists()
        )


class IsClassAdmin(BasePermission):
    """
    Require the current user to be an ADMIN member of the classroom.
    Assumes view has `get_classroom()` method.
    """

    message = "You do not have permission to manage this class."

    def has_permission(self, request, view):
        classroom = getattr(view, "get_classroom", lambda: None)()
        if classroom is None:
            return False
        return (
            classroom.memberships.filter(user=request.user, role="ADMIN")
            .exclude(status=ClassroomMembership.STATUS_REMOVED)
            .exists()
        )


# ── Capability-backed permissions (BUSINESS-ARCHITECTURE §2) ──────────────────
# These derive from classes.capabilities.classroom_capabilities (role → capability +
# global-admin override) so authorization is consistent and TA-aware. Views must expose
# `get_classroom()`.

from .capabilities import classroom_capabilities  # noqa: E402


class _CapabilityPermission(BasePermission):
    capability = ""  # attribute name on Capabilities

    def has_permission(self, request, view):
        classroom = getattr(view, "get_classroom", lambda: None)()
        if classroom is None:
            return False
        caps = classroom_capabilities(request.user, classroom)
        return bool(getattr(caps, self.capability, False))


class IsClassMemberCap(_CapabilityPermission):
    message = "You are not a member of this class."
    capability = "is_member"


class CanManageClass(_CapabilityPermission):
    message = "You do not have permission to manage this class."
    capability = "can_manage_class"


class CanManageAssignments(_CapabilityPermission):
    message = "You do not have permission to manage assignments."
    capability = "can_manage_assignments"


class CanGrade(_CapabilityPermission):
    message = "You do not have permission to grade in this class."
    capability = "can_grade"


class CanTakeAttendance(_CapabilityPermission):
    message = "You do not have permission to manage attendance."
    capability = "can_take_attendance"


class CanConfigureRanking(_CapabilityPermission):
    message = "You do not have permission to configure rankings."
    capability = "can_configure_ranking"


class CanRecomputeRanking(_CapabilityPermission):
    message = "You do not have permission to recompute rankings."
    capability = "can_recompute_ranking"

