"""
ClassroomAccessService — classroom-driven access.

When a teacher assigns a resource inside a classroom, every currently-enrolled
student must receive a RESOURCE grant **transactionally**: all-or-nothing. When a
student joins a classroom, they receive grants for that classroom's existing
assignments. Replaces the legacy signal/backfill sync (``classes/models.py``).
"""

from __future__ import annotations

from typing import Iterable

from django.db import transaction

from access.models import ResourceAccessGrant

from .assignment_service import AssignmentService


class ClassroomAccessService:
    @staticmethod
    def _student_user_ids(classroom) -> list[int]:
        from classes.models import ClassroomMembership

        return list(
            classroom.memberships.filter(
                role=ClassroomMembership.ROLE_STUDENT
            ).values_list("user_id", flat=True)
        )

    @classmethod
    @transaction.atomic
    def assign_resource_to_classroom(
        cls, classroom, resource_type, resource_id, *, actor=None, expires_at=None,
        note="", require_exists=True,
    ) -> dict:
        """
        Grant ``(resource_type, resource_id)`` to all enrolled students in one
        transaction. If anything raises, the whole assignment rolls back — no
        partially-granted classroom (the brief's hard requirement).
        """
        from django.contrib.auth import get_user_model

        User = get_user_model()
        user_ids = cls._student_user_ids(classroom)
        users = list(User.objects.filter(pk__in=user_ids))
        result = AssignmentService.bulk_assign_resource(
            users, resource_type, resource_id,
            actor=actor, source=ResourceAccessGrant.SOURCE_CLASSROOM,
            classroom=classroom, expires_at=expires_at, note=note or "classroom assignment",
            require_exists=require_exists,
        )
        result["classroom_id"] = getattr(classroom, "pk", classroom)
        result["resource_type"] = resource_type
        result["resource_id"] = resource_id
        return result

    @classmethod
    @transaction.atomic
    def assign_targets_to_classroom(
        cls, classroom, targets, *, actor=None, expires_at=None, note="", require_exists=True,
    ) -> dict:
        """Grant several resource targets (e.g. expanded pack sections) to all enrolled students, atomically."""
        from django.contrib.auth import get_user_model

        User = get_user_model()
        users = list(User.objects.filter(pk__in=cls._student_user_ids(classroom)))
        result = AssignmentService.bulk_assign_targets(
            users, targets, actor=actor, source=ResourceAccessGrant.SOURCE_CLASSROOM,
            classroom=classroom, expires_at=expires_at, note=note or "classroom assignment",
            require_exists=require_exists,
        )
        result["classroom_id"] = getattr(classroom, "pk", classroom)
        return result

    @classmethod
    @transaction.atomic
    def on_student_enrolled(cls, classroom, user, *, actor=None) -> dict:
        """
        Backfill grants for a newly-enrolled student from this classroom's existing
        resource assignments (distinct active CLASSROOM grants already issued to the
        class). Transactional and idempotent.
        """
        assignments = (
            ResourceAccessGrant.objects.filter(
                classroom=classroom,
                scope=ResourceAccessGrant.SCOPE_RESOURCE,
                source=ResourceAccessGrant.SOURCE_CLASSROOM,
                status=ResourceAccessGrant.STATUS_ACTIVE,
            )
            .values_list("resource_type", "resource_id")
            .distinct()
        )
        created = 0
        for rt, rid in assignments:
            grant = AssignmentService.assign_resource(
                user, rt, rid, actor=actor,
                source=ResourceAccessGrant.SOURCE_CLASSROOM, classroom=classroom,
                note="enroll backfill", require_exists=False,
            )
            if grant.source == ResourceAccessGrant.SOURCE_CLASSROOM:
                created += 1
        return {
            "classroom_id": getattr(classroom, "pk", classroom),
            "user_id": getattr(user, "pk", user),
            "assignments_synced": created,
        }

    @classmethod
    @transaction.atomic
    def revoke_classroom_assignment(
        cls, classroom, resource_type, resource_id, *, actor=None, note=""
    ) -> int:
        """Revoke a classroom-sourced resource grant from all enrolled students."""
        from .access_service import AccessService

        grants = ResourceAccessGrant.objects.select_for_update().filter(
            classroom=classroom,
            scope=ResourceAccessGrant.SCOPE_RESOURCE,
            resource_type=resource_type,
            resource_id=resource_id,
            status=ResourceAccessGrant.STATUS_ACTIVE,
        )
        n = 0
        for g in list(grants):
            AccessService.revoke(g, actor=actor, note=note or "classroom revoke")
            n += 1
        return n
