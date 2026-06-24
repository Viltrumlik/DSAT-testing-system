"""
VisibilityService — the single authority for "may this user see/use this resource".

Decision (see docs/access-redesign/02-architecture.md §5):

    staff RBAC on the resource's subject(s)
      OR an ACTIVE, non-expired RESOURCE grant for (user, type, id)
      OR an ACTIVE, non-expired SUBJECT grant covering ALL the resource's subjects

Students are governed purely by grants; staff by the existing RBAC helpers (kept
as the single source of truth for authoring/library scope so this layer does not
fork authorization).
"""

from __future__ import annotations

from typing import Optional

from django.db.models import Q
from django.utils import timezone

from access import resources
from access.models import ResourceAccessGrant
from access.services import (
    can_view_tests,
    is_global_scope_staff,
    normalized_role,
)
from access.subject_mapping import domain_subject_to_platform
from access import constants


class VisibilityService:
    # -- helpers ---------------------------------------------------------

    @staticmethod
    def _authed(user) -> bool:
        return bool(user and getattr(user, "is_authenticated", False))

    @staticmethod
    def _is_student(user) -> bool:
        return normalized_role(user) == constants.ROLE_STUDENT

    @classmethod
    def _staff_can_view(cls, user, domains: frozenset) -> bool:
        """Staff RBAC visibility for a resource with the given domain subjects."""
        if cls._is_student(user):
            return False
        if not domains:
            # Empty/unknown subject (e.g. empty mock shell): global staff only.
            return is_global_scope_staff(user)
        return all(
            can_view_tests(user, domain_subject_to_platform(d)) for d in domains
        )

    @classmethod
    def active_subject_domains(cls, user, *, now=None) -> frozenset[str]:
        """Domain subjects the user holds an effective GLOBAL subject grant for."""
        now = now or timezone.now()
        qs = ResourceAccessGrant.objects.filter(
            user=user,
            scope=ResourceAccessGrant.SCOPE_SUBJECT,
            status=ResourceAccessGrant.STATUS_ACTIVE,
            classroom__isnull=True,
        ).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
        return frozenset(qs.values_list("subject", flat=True))

    @classmethod
    def _has_resource_grant(cls, user, resource_type, resource_id, *, now=None) -> bool:
        now = now or timezone.now()
        return (
            ResourceAccessGrant.objects.filter(
                user=user,
                scope=ResourceAccessGrant.SCOPE_RESOURCE,
                resource_type=resource_type,
                resource_id=resource_id,
                status=ResourceAccessGrant.STATUS_ACTIVE,
            )
            .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
            .exists()
        )

    # -- public API ------------------------------------------------------

    @classmethod
    def can_access(
        cls, user, resource_type: str, resource_id: int, *, instance=None, now=None
    ) -> bool:
        if not cls._authed(user):
            return False
        rt = resources.get(resource_type)
        if rt is None:
            return False
        now = now or timezone.now()

        if instance is None:
            instance = rt.get_instance(resource_id)
        domains = rt.domain_subjects(instance)

        # 1) Staff RBAC.
        if cls._staff_can_view(user, domains):
            return True
        # 2) Direct resource grant.
        if cls._has_resource_grant(user, resource_type, resource_id, now=now):
            return True
        # 3) Subject coverage — all of the resource's subjects must be held.
        if domains and domains.issubset(cls.active_subject_domains(user, now=now)):
            return True
        return False

    @classmethod
    def filter_visible(cls, user, resource_type: str, queryset, *, now=None):
        """
        Restrict ``queryset`` (of the resource type's model) to rows the user may see.

        Students: resource grants OR subject-grant coverage. Staff: governed by RBAC
        at the permission layer — returned unchanged here so this service never
        widens or narrows staff library scope (parity-preserving).
        """
        if not cls._authed(user):
            return queryset.none()
        rt = resources.get(resource_type)
        if rt is None:
            return queryset.none()
        if not cls._is_student(user):
            return queryset
        now = now or timezone.now()

        resource_ids = (
            ResourceAccessGrant.objects.filter(
                user=user,
                scope=ResourceAccessGrant.SCOPE_RESOURCE,
                resource_type=resource_type,
                status=ResourceAccessGrant.STATUS_ACTIVE,
            )
            .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
            .values_list("resource_id", flat=True)
        )
        q = Q(pk__in=resource_ids)

        domains = cls.active_subject_domains(user, now=now)
        if domains and rt.subject_queryset_resolver is not None:
            covered = rt.subject_queryset_resolver(queryset, domains)
            q |= Q(pk__in=covered.values_list("pk", flat=True))

        return queryset.filter(q).distinct()
