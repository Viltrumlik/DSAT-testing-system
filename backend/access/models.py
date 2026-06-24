from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from . import constants


class UserAccess(models.Model):
    """
    DB-backed access grant: user may act within a domain subject globally or for one classroom.

    Uniqueness on (user, subject, classroom) prevents duplicate rows. ``granted_by`` is set on
    create and **refreshed on each duplicate POST** to ``/api/access/grant/`` (latest actor wins;
    there is no separate historical audit table).
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="access_grants",
    )
    subject = models.CharField(
        max_length=16,
        choices=[(constants.DOMAIN_MATH, "Math"), (constants.DOMAIN_ENGLISH, "English")],
        db_index=True,
    )
    classroom = models.ForeignKey(
        "classes.Classroom",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="access_grants",
    )
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="access_grants_given",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        super().clean()
        if self.subject not in constants.ALL_DOMAIN_SUBJECTS:
            raise ValidationError(
                {"subject": f"Must be one of: {', '.join(constants.ALL_DOMAIN_SUBJECTS)}."}
            )

    class Meta:
        db_table = "access_user_access"
        indexes = [
            models.Index(fields=["user", "subject"]),
            models.Index(fields=["user", "subject", "classroom"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "subject", "classroom"],
                name="access_user_access_unique_user_subject_classroom",
            )
        ]

    def __str__(self) -> str:
        c = f" class={self.classroom_id}" if self.classroom_id else " global"
        return f"{self.user_id} {self.subject}{c}"


class Permission(models.Model):
    codename = models.SlugField(max_length=64, unique=True, db_index=True)
    name = models.CharField(max_length=128)
    description = models.TextField(blank=True)

    class Meta:
        db_table = "access_permissions"
        ordering = ["codename"]

    def __str__(self):
        return self.codename


class Role(models.Model):
    code = models.SlugField(max_length=32, unique=True, db_index=True)
    name = models.CharField(max_length=64)
    description = models.TextField(blank=True)

    permissions = models.ManyToManyField(
        Permission,
        through="RolePermission",
        related_name="roles",
        blank=True,
    )

    class Meta:
        db_table = "access_roles"
        ordering = ["code"]

    def __str__(self):
        return f"{self.code}"


class RolePermission(models.Model):
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="role_permissions")
    permission = models.ForeignKey(
        Permission, on_delete=models.CASCADE, related_name="role_permissions"
    )

    class Meta:
        db_table = "access_role_permissions"
        unique_together = [("role", "permission")]


class UserPermission(models.Model):
    """Optional per-user grant (True) or explicit deny (False). Deny wins over role."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="access_overrides",
    )
    permission = models.ForeignKey(
        Permission, on_delete=models.CASCADE, related_name="user_overrides"
    )
    granted = models.BooleanField(default=True)

    class Meta:
        db_table = "access_user_permissions"
        unique_together = [("user", "permission")]

    def clean(self) -> None:
        super().clean()
        from access.services import normalized_role

        role = normalized_role(self.user)
        if (
            self.granted
            and role == constants.ROLE_STUDENT
            and self.permission.codename in constants.PERMISSIONS_STUDENT_OVERRIDE_DENIED
        ):
            raise ValidationError(
                {
                    "permission": (
                        "Students cannot be granted this permission via override; "
                        "subject-scoped staff permissions are not transferable."
                    )
                }
            )


# ---------------------------------------------------------------------------
# Centralized access engine (Phase 2) — hybrid SUBJECT + RESOURCE grants.
#
# This is the new single source of truth for "may this user use this resource".
# It coexists with the legacy ``UserAccess`` / per-resource M2M tables and is
# inert in production until the ``ACCESS_ENGINE_*`` feature flags are enabled.
# See docs/access-redesign/.
# ---------------------------------------------------------------------------


class ResourceAccessGrant(models.Model):
    """
    One row = one grant of access to a user, at one of two scopes:

    * ``SUBJECT``  — covers a whole domain subject (``math`` / ``english``),
      optionally scoped to a single classroom. ``subject`` set; ``resource_*`` null.
    * ``RESOURCE`` — covers one concrete resource (a practice test, mock exam,
      assessment set, …) identified by ``(resource_type, resource_id)`` resolved
      through :mod:`access.resources`. ``resource_*`` set; ``subject`` null.

    Grants carry lifecycle (:attr:`status`, :attr:`expires_at`), provenance
    (:attr:`source`, :attr:`granted_by`, :attr:`classroom`) and an immutable
    audit trail via :class:`AccessGrantEvent`. Mutate **only** through
    :mod:`access.engine` services so audit + dedup stay consistent.
    """

    SCOPE_SUBJECT = "SUBJECT"
    SCOPE_RESOURCE = "RESOURCE"
    SCOPE_CHOICES = [(SCOPE_SUBJECT, "Subject"), (SCOPE_RESOURCE, "Resource")]

    SOURCE_MANUAL = "MANUAL"
    SOURCE_BULK = "BULK"
    SOURCE_CLASSROOM = "CLASSROOM"
    SOURCE_PURCHASE = "PURCHASE"
    SOURCE_SYSTEM = "SYSTEM"
    SOURCE_CHOICES = [
        (SOURCE_MANUAL, "Manual"),
        (SOURCE_BULK, "Bulk"),
        (SOURCE_CLASSROOM, "Classroom"),
        (SOURCE_PURCHASE, "Purchase"),
        (SOURCE_SYSTEM, "System / backfill"),
    ]

    STATUS_ACTIVE = "ACTIVE"
    STATUS_REVOKED = "REVOKED"
    STATUS_EXPIRED = "EXPIRED"
    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_REVOKED, "Revoked"),
        (STATUS_EXPIRED, "Expired"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="resource_access_grants",
    )
    scope = models.CharField(max_length=8, choices=SCOPE_CHOICES, db_index=True)

    # SUBJECT scope
    subject = models.CharField(
        max_length=16,
        null=True,
        blank=True,
        db_index=True,
        help_text="Domain subject (math/english) for SUBJECT grants; NULL for RESOURCE grants.",
    )

    # RESOURCE scope (logical polymorphic FK resolved via access.resources)
    resource_type = models.CharField(max_length=32, null=True, blank=True, db_index=True)
    resource_id = models.BigIntegerField(null=True, blank=True, db_index=True)

    # Optional provenance / scoping context.
    classroom = models.ForeignKey(
        "classes.Classroom",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="resource_access_grants",
    )

    source = models.CharField(max_length=12, choices=SOURCE_CHOICES, default=SOURCE_MANUAL, db_index=True)
    status = models.CharField(max_length=8, choices=STATUS_CHOICES, default=STATUS_ACTIVE, db_index=True)

    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resource_access_grants_given",
    )
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "resource_access_grants"
        indexes = [
            models.Index(fields=["user", "status", "scope"], name="rag_user_status_scope"),
            models.Index(
                fields=["user", "status", "scope", "resource_type", "resource_id"],
                name="rag_user_resource",
            ),
            models.Index(
                fields=["user", "status", "scope", "subject", "classroom"],
                name="rag_user_subject",
            ),
            models.Index(
                fields=["resource_type", "resource_id", "status"], name="rag_resource_reverse"
            ),
            models.Index(fields=["status", "expires_at"], name="rag_expiry_sweep"),
            models.Index(fields=["classroom", "status"], name="rag_classroom_status"),
        ]
        constraints = [
            models.CheckConstraint(
                name="rag_scope_shape",
                condition=(
                    models.Q(
                        scope="SUBJECT",
                        subject__isnull=False,
                        resource_type__isnull=True,
                        resource_id__isnull=True,
                    )
                    | models.Q(
                        scope="RESOURCE",
                        subject__isnull=True,
                        resource_type__isnull=False,
                        resource_id__isnull=False,
                    )
                ),
            ),
            # Exactly one ACTIVE grant per logical target. Split on classroom NULL /
            # NOT NULL because NULLs are distinct in unique indexes.
            models.UniqueConstraint(
                fields=["user", "subject"],
                condition=models.Q(status="ACTIVE", scope="SUBJECT", classroom__isnull=True),
                name="rag_uniq_active_subject_global",
            ),
            models.UniqueConstraint(
                fields=["user", "subject", "classroom"],
                condition=models.Q(status="ACTIVE", scope="SUBJECT", classroom__isnull=False),
                name="rag_uniq_active_subject_classroom",
            ),
            models.UniqueConstraint(
                fields=["user", "resource_type", "resource_id"],
                condition=models.Q(status="ACTIVE", scope="RESOURCE", classroom__isnull=True),
                name="rag_uniq_active_resource_global",
            ),
            models.UniqueConstraint(
                fields=["user", "resource_type", "resource_id", "classroom"],
                condition=models.Q(status="ACTIVE", scope="RESOURCE", classroom__isnull=False),
                name="rag_uniq_active_resource_classroom",
            ),
        ]

    def __str__(self) -> str:
        if self.scope == self.SCOPE_SUBJECT:
            tgt = f"subject={self.subject}"
        else:
            tgt = f"{self.resource_type}#{self.resource_id}"
        c = f" class={self.classroom_id}" if self.classroom_id else ""
        return f"grant<{self.user_id} {tgt}{c} {self.status}>"

    def is_effective(self, now=None) -> bool:
        """ACTIVE and not past its expiry."""
        if self.status != self.STATUS_ACTIVE:
            return False
        if self.expires_at is None:
            return True
        return self.expires_at > (now or timezone.now())

    def clean(self) -> None:
        super().clean()
        if self.scope == self.SCOPE_SUBJECT:
            if not self.subject:
                raise ValidationError({"subject": "SUBJECT grants require a subject."})
            if self.resource_type or self.resource_id:
                raise ValidationError({"resource_type": "SUBJECT grants must not set resource_*."})
            if self.subject not in constants.ALL_DOMAIN_SUBJECTS:
                raise ValidationError(
                    {"subject": f"Must be one of: {', '.join(constants.ALL_DOMAIN_SUBJECTS)}."}
                )
        elif self.scope == self.SCOPE_RESOURCE:
            if not self.resource_type or self.resource_id is None:
                raise ValidationError(
                    {"resource_type": "RESOURCE grants require resource_type and resource_id."}
                )
            if self.subject:
                raise ValidationError({"subject": "RESOURCE grants must not set subject."})
        else:
            raise ValidationError({"scope": "scope must be SUBJECT or RESOURCE."})


class AccessGrantEvent(models.Model):
    """Append-only audit record for every state change of a grant. Never updated/deleted."""

    ACTION_GRANTED = "GRANTED"
    ACTION_REVOKED = "REVOKED"
    ACTION_EXPIRED = "EXPIRED"
    ACTION_EXTENDED = "EXTENDED"
    ACTION_RESTORED = "RESTORED"
    ACTION_BACKFILLED = "BACKFILLED"
    ACTION_CHOICES = [
        (ACTION_GRANTED, "Granted"),
        (ACTION_REVOKED, "Revoked"),
        (ACTION_EXPIRED, "Expired"),
        (ACTION_EXTENDED, "Extended"),
        (ACTION_RESTORED, "Restored"),
        (ACTION_BACKFILLED, "Backfilled"),
    ]

    grant = models.ForeignKey(
        ResourceAccessGrant, on_delete=models.CASCADE, related_name="events"
    )
    action = models.CharField(max_length=12, choices=ACTION_CHOICES, db_index=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="access_grant_events_authored",
    )
    snapshot = models.JSONField(default=dict, blank=True)
    note = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "access_grant_events"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["grant", "created_at"], name="age_grant_created"),
            models.Index(fields=["action", "created_at"], name="age_action_created"),
        ]

    def __str__(self) -> str:
        return f"event<{self.action} grant={self.grant_id} @{self.created_at:%Y-%m-%d}>"
