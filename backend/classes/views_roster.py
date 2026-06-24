"""Roster / member management API (TA rollout).

PATCH /api/classes/<pk>/members/<user_id>/  { role?, status? }

Per the finalized capability matrix:
  - Assigning/revoking TA or TEACHER (role change)  → Owner only (can_assign_ta)
  - Removing/restoring a STUDENT (status change)      → Teacher+Owner (can_manage_roster)
The class owner's membership can never be changed or removed here.
"""

from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import status as http
from rest_framework.response import Response

from .capabilities import classroom_capabilities
from .models import ClassroomMembership
from .views_rankings import _ClassroomScopedView, _display_name

_ASSIGNABLE_ROLES = {ClassroomMembership.ROLE_TA, ClassroomMembership.ROLE_TEACHER, ClassroomMembership.ROLE_STUDENT}
_OWNER_ROLES = {ClassroomMembership.ROLE_OWNER, ClassroomMembership.ROLE_ADMIN}


class MemberManageView(_ClassroomScopedView):
    def patch(self, request, classroom_pk, user_id):
        classroom = self.get_classroom()
        caps = classroom_capabilities(request.user, classroom)
        membership = get_object_or_404(ClassroomMembership, classroom=classroom, user_id=user_id)

        if membership.role in _OWNER_ROLES:
            return Response({"detail": "The class owner cannot be modified here."}, status=http.HTTP_400_BAD_REQUEST)

        new_role = request.data.get("role")
        new_status = request.data.get("status")
        if new_role is None and new_status is None:
            return Response({"detail": "Provide role and/or status."}, status=http.HTTP_400_BAD_REQUEST)

        if new_role is not None:
            if new_role not in _ASSIGNABLE_ROLES:
                return Response({"detail": "Invalid role."}, status=http.HTTP_400_BAD_REQUEST)
            # Promoting/demoting between staff and student is an ownership decision.
            if not caps.can_assign_ta:
                return Response({"detail": "Only the class owner can change member roles."}, status=http.HTTP_403_FORBIDDEN)
            membership.role = new_role

        if new_status is not None:
            if new_status not in (ClassroomMembership.STATUS_ACTIVE, ClassroomMembership.STATUS_REMOVED):
                return Response({"detail": "Invalid status."}, status=http.HTTP_400_BAD_REQUEST)
            target_is_staff = membership.role in ClassroomMembership.STAFF_ROLES
            allowed = caps.can_assign_ta if target_is_staff else caps.can_manage_roster
            if not allowed:
                return Response({"detail": "You do not have permission to change this member."}, status=http.HTTP_403_FORBIDDEN)
            membership.status = new_status

        membership.save(update_fields=["role", "status"])
        return Response({
            "user_id": membership.user_id,
            "name": _display_name(membership.user),
            "role": membership.role,
            "status": membership.status,
        })
