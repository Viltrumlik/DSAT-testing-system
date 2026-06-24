"""
AccessService — low-level grant lifecycle. The only code that creates/mutates
``ResourceAccessGrant`` rows and writes the ``AccessGrantEvent`` audit trail.

Higher-level flows (manual/bulk/classroom) compose these primitives via
:class:`AssignmentService` / :class:`ClassroomAccessService`. Views/admin must not
touch grant rows directly.
"""

from __future__ import annotations

from typing import Optional

from django.db import transaction
from django.utils import timezone

from access.models import AccessGrantEvent, ResourceAccessGrant


def _snapshot(grant: ResourceAccessGrant) -> dict:
    return {
        "id": grant.pk,
        "user_id": grant.user_id,
        "scope": grant.scope,
        "subject": grant.subject,
        "resource_type": grant.resource_type,
        "resource_id": grant.resource_id,
        "classroom_id": grant.classroom_id,
        "source": grant.source,
        "status": grant.status,
        "expires_at": grant.expires_at.isoformat() if grant.expires_at else None,
    }


class AccessService:
    """Stateless namespace of grant primitives (all classmethods)."""

    # -- internal --------------------------------------------------------

    @staticmethod
    def _log(grant, action, *, actor=None, note="") -> None:
        AccessGrantEvent.objects.create(
            grant=grant, action=action, actor=actor, note=note, snapshot=_snapshot(grant)
        )

    @classmethod
    def _active_lookup(cls, **target) -> dict:
        """Build a filter for the single ACTIVE grant matching a logical target."""
        return {"status": ResourceAccessGrant.STATUS_ACTIVE, **target}

    # -- subject grants --------------------------------------------------

    @classmethod
    @transaction.atomic
    def grant_subject(
        cls,
        user,
        subject: str,
        *,
        source: str = ResourceAccessGrant.SOURCE_MANUAL,
        granted_by=None,
        classroom=None,
        expires_at=None,
        note: str = "",
        _event: str = AccessGrantEvent.ACTION_GRANTED,
    ) -> ResourceAccessGrant:
        """Idempotent: returns the existing ACTIVE subject grant or creates one."""
        classroom_id = getattr(classroom, "pk", classroom)
        existing = (
            ResourceAccessGrant.objects.select_for_update()
            .filter(
                **cls._active_lookup(
                    user=user,
                    scope=ResourceAccessGrant.SCOPE_SUBJECT,
                    subject=subject,
                    classroom_id=classroom_id,
                )
            )
            .first()
        )
        if existing:
            return existing
        grant = ResourceAccessGrant.objects.create(
            user=user,
            scope=ResourceAccessGrant.SCOPE_SUBJECT,
            subject=subject,
            classroom_id=classroom_id,
            source=source,
            status=ResourceAccessGrant.STATUS_ACTIVE,
            granted_by=granted_by,
            expires_at=expires_at,
        )
        cls._log(grant, _event, actor=granted_by, note=note)
        return grant

    # -- resource grants -------------------------------------------------

    @classmethod
    @transaction.atomic
    def grant_resource(
        cls,
        user,
        resource_type: str,
        resource_id: int,
        *,
        source: str = ResourceAccessGrant.SOURCE_MANUAL,
        granted_by=None,
        classroom=None,
        expires_at=None,
        note: str = "",
        _event: str = AccessGrantEvent.ACTION_GRANTED,
    ) -> ResourceAccessGrant:
        """Idempotent: returns the existing ACTIVE resource grant or creates one."""
        classroom_id = getattr(classroom, "pk", classroom)
        existing = (
            ResourceAccessGrant.objects.select_for_update()
            .filter(
                **cls._active_lookup(
                    user=user,
                    scope=ResourceAccessGrant.SCOPE_RESOURCE,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    classroom_id=classroom_id,
                )
            )
            .first()
        )
        if existing:
            return existing
        grant = ResourceAccessGrant.objects.create(
            user=user,
            scope=ResourceAccessGrant.SCOPE_RESOURCE,
            resource_type=resource_type,
            resource_id=resource_id,
            classroom_id=classroom_id,
            source=source,
            status=ResourceAccessGrant.STATUS_ACTIVE,
            granted_by=granted_by,
            expires_at=expires_at,
        )
        cls._log(grant, _event, actor=granted_by, note=note)
        return grant

    # -- lifecycle -------------------------------------------------------

    @classmethod
    @transaction.atomic
    def revoke(cls, grant: ResourceAccessGrant, *, actor=None, note: str = "") -> ResourceAccessGrant:
        grant = ResourceAccessGrant.objects.select_for_update().get(pk=grant.pk)
        if grant.status == ResourceAccessGrant.STATUS_REVOKED:
            return grant
        grant.status = ResourceAccessGrant.STATUS_REVOKED
        grant.save(update_fields=["status", "updated_at"])
        cls._log(grant, AccessGrantEvent.ACTION_REVOKED, actor=actor, note=note)
        return grant

    @classmethod
    @transaction.atomic
    def extend(
        cls, grant: ResourceAccessGrant, *, expires_at, actor=None, note: str = ""
    ) -> ResourceAccessGrant:
        grant = ResourceAccessGrant.objects.select_for_update().get(pk=grant.pk)
        grant.expires_at = expires_at
        # Re-activate if it had lapsed to EXPIRED but is being extended into the future.
        if grant.status == ResourceAccessGrant.STATUS_EXPIRED and (
            expires_at is None or expires_at > timezone.now()
        ):
            grant.status = ResourceAccessGrant.STATUS_ACTIVE
        grant.save(update_fields=["expires_at", "status", "updated_at"])
        cls._log(grant, AccessGrantEvent.ACTION_EXTENDED, actor=actor, note=note)
        return grant

    @classmethod
    def expire_due(cls, *, now=None, batch_size: int = 1000) -> int:
        """
        Sweep ACTIVE grants past their expiry into EXPIRED. Returns count.

        Idempotent and safe to run on a schedule. Writes one audit event per grant.
        """
        now = now or timezone.now()
        total = 0
        while True:
            ids = list(
                ResourceAccessGrant.objects.filter(
                    status=ResourceAccessGrant.STATUS_ACTIVE,
                    expires_at__isnull=False,
                    expires_at__lte=now,
                ).values_list("pk", flat=True)[:batch_size]
            )
            if not ids:
                break
            with transaction.atomic():
                grants = list(
                    ResourceAccessGrant.objects.select_for_update().filter(pk__in=ids)
                )
                for g in grants:
                    if g.status != ResourceAccessGrant.STATUS_ACTIVE:
                        continue
                    g.status = ResourceAccessGrant.STATUS_EXPIRED
                    g.save(update_fields=["status", "updated_at"])
                    cls._log(g, AccessGrantEvent.ACTION_EXPIRED, note="auto-expired")
                    total += 1
            if len(ids) < batch_size:
                break
        return total
