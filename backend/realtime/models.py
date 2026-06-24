from __future__ import annotations

from django.conf import settings
from django.db import models

from .constants import PRIORITY_CHOICES, PRIORITY_MEDIUM


class RealtimeEvent(models.Model):
    """
    Durable outbox for push delivery (SSE/WebSocket).

    Events are *delivery hints only*; clients still refetch canonical REST endpoints.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="realtime_events",
        db_index=True,
    )
    event_type = models.CharField(max_length=64, db_index=True)
    priority = models.CharField(max_length=16, choices=PRIORITY_CHOICES, default=PRIORITY_MEDIUM, db_index=True)
    dedupe_key = models.CharField(max_length=64, blank=True, db_index=True)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "realtime_events"
        ordering = ["id"]
        indexes = [
            models.Index(fields=["user", "id"]),
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["user", "dedupe_key", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"RealtimeEvent#{self.pk} {self.event_type} user={self.user_id}"


class IncidentReview(models.Model):
    """
    Minimal incident review system (DB-backed).
    """

    SEVERITY_CHOICES = [
        ("sev1", "SEV1"),
        ("sev2", "SEV2"),
        ("sev3", "SEV3"),
    ]
    STATUS_CHOICES = [
        ("open", "Open"),
        ("reviewed", "Reviewed"),
        ("closed", "Closed"),
    ]

    started_at = models.DateTimeField(db_index=True)
    ended_at = models.DateTimeField(null=True, blank=True, db_index=True)
    severity = models.CharField(max_length=16, choices=SEVERITY_CHOICES, db_index=True, default="sev2")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, db_index=True, default="open")

    summary = models.CharField(max_length=255, db_index=True, default="")
    root_cause = models.TextField(blank=True, default="")
    prevention_action = models.TextField(blank=True, default="")

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="incident_reviews_created",
        null=True,
        blank=True,
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="incident_reviews_updated",
        null=True,
        blank=True,
    )
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        db_table = "ops_incident_reviews"
        ordering = ["-started_at", "-id"]
        indexes = [
            models.Index(fields=["severity", "status", "started_at"]),
        ]

    @staticmethod
    def from_payload(*, data: dict, actor):
        from django.utils import timezone

        started_at = data.get("started_at") or timezone.now().isoformat()
        try:
            started_at_dt = timezone.datetime.fromisoformat(str(started_at).replace("Z", "+00:00"))
        except Exception:
            started_at_dt = timezone.now()

        row = IncidentReview.objects.create(
            started_at=started_at_dt,
            severity=str(data.get("severity") or "sev2")[:16],
            status="open",
            summary=str(data.get("summary") or "")[:255],
            root_cause=str(data.get("root_cause") or ""),
            prevention_action=str(data.get("prevention_action") or ""),
            created_by=actor if getattr(actor, "is_authenticated", False) else None,
            updated_by=actor if getattr(actor, "is_authenticated", False) else None,
        )
        return row

    def apply_patch(self, *, data: dict, actor) -> None:
        from django.utils import timezone

        if "ended_at" in data:
            raw = data.get("ended_at")
            if raw in (None, "", False):
                self.ended_at = None
            else:
                try:
                    self.ended_at = timezone.datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
                except Exception:
                    pass
        if "severity" in data:
            self.severity = str(data.get("severity") or self.severity)[:16]
        if "status" in data:
            self.status = str(data.get("status") or self.status)[:16]
        if "summary" in data:
            self.summary = str(data.get("summary") or self.summary)[:255]
        if "root_cause" in data:
            self.root_cause = str(data.get("root_cause") or "")
        if "prevention_action" in data:
            self.prevention_action = str(data.get("prevention_action") or "")
        if getattr(actor, "is_authenticated", False):
            self.updated_by = actor
        self.save()

    def to_dict(self) -> dict:
        return {
            "id": int(self.pk),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "severity": self.severity,
            "status": self.status,
            "summary": self.summary,
            "root_cause": self.root_cause,
            "prevention_action": self.prevention_action,
            "created_by_id": self.created_by_id,
            "updated_by_id": self.updated_by_id,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

