"""View/action-level authorization for exams bulk-assign APIs."""

from __future__ import annotations

from rest_framework.permissions import BasePermission

from . import constants
from .services import (
    actor_subject_probe_for_domain_perm,
    authorize,
    bulk_assign_request_platform_subjects,
    get_effective_permission_codenames,
)


class BulkAssignAccess(BasePermission):
    def has_permission(self, request, view):
        subjects = bulk_assign_request_platform_subjects(request.data or {})
        if not subjects:
            return False
        return all(
            authorize(request.user, constants.PERM_ASSIGN_ACCESS, subject=s)
            for s in subjects
        )


class BulkAssignmentHistoryAccess(BasePermission):
    """
    List / re-run library bulk-assignment history (no request body on GET).

    Mirrors who may use the admin Assignments console: assign_access or manage_users
    in the actor's platform subject context, plus wildcard.
    """

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        perms = get_effective_permission_codenames(user)
        if constants.WILDCARD in perms:
            return True
        subj = actor_subject_probe_for_domain_perm(user)
        if not subj:
            return False
        return authorize(user, constants.PERM_ASSIGN_ACCESS, subject=subj) or authorize(
            user, constants.PERM_MANAGE_USERS, subject=subj
        )
