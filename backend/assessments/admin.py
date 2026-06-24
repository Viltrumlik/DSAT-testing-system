from django.contrib import admin

from .models import (
    AssessmentSet,
    AssessmentSetVersion,
    AssessmentQuestion,
    HomeworkAssignment,
    AssessmentAttempt,
    AssessmentAnswer,
    AssessmentResult,
    SecurityAlert,
    GovernanceEvent,
)


@admin.register(AssessmentSetVersion)
class AssessmentSetVersionAdmin(admin.ModelAdmin):
    """
    IMMUTABLE RECORD — read-only in admin. Never allow edits or deletes.
    All fields are readonly to prevent accidental modification of academic records.
    """

    list_display = (
        "id",
        "assessment_set",
        "version_number",
        "question_count",
        "snapshot_checksum_short",
        "published_by",
        "published_at",
    )
    list_filter = ("published_at",)
    search_fields = ("assessment_set__title", "published_by__email", "snapshot_checksum")
    ordering = ("-published_at", "-version_number")

    # All fields readonly — immutable records cannot be edited.
    readonly_fields = (
        "assessment_set",
        "version_number",
        "snapshot_json",
        "snapshot_checksum",
        "question_count",
        "published_by",
        "published_at",
    )

    def snapshot_checksum_short(self, obj):
        return obj.snapshot_checksum[:12] + "…" if obj.snapshot_checksum else ""

    snapshot_checksum_short.short_description = "Checksum"

    def has_add_permission(self, request):
        return False  # Versions are created only via publish_assessment_set()

    def has_change_permission(self, request, obj=None):
        return False  # Immutable

    def has_delete_permission(self, request, obj=None):
        return False  # Permanent academic records


@admin.register(AssessmentSet)
class AssessmentSetAdmin(admin.ModelAdmin):
    list_display = ("id", "subject", "category", "title", "is_active", "created_at")
    list_filter = ("subject", "is_active", "created_at")
    search_fields = ("title", "category", "description")


@admin.register(AssessmentQuestion)
class AssessmentQuestionAdmin(admin.ModelAdmin):
    list_display = ("id", "assessment_set", "order", "question_type", "points", "is_active", "created_at")
    list_filter = ("question_type", "is_active")
    search_fields = ("prompt",)


@admin.register(HomeworkAssignment)
class HomeworkAssignmentAdmin(admin.ModelAdmin):
    list_display = ("id", "classroom", "assessment_set", "assignment", "assigned_by", "created_at")
    list_filter = ("created_at",)
    search_fields = ("assignment__title", "assessment_set__title", "classroom__name", "assigned_by__email")


@admin.register(AssessmentAttempt)
class AssessmentAttemptAdmin(admin.ModelAdmin):
    list_display = ("id", "homework", "student", "status", "started_at", "submitted_at", "total_time_seconds")
    list_filter = ("status", "started_at", "submitted_at")
    search_fields = ("student__email", "student__username")


@admin.register(AssessmentAnswer)
class AssessmentAnswerAdmin(admin.ModelAdmin):
    list_display = ("id", "attempt", "question", "is_correct", "points_awarded", "time_spent_seconds", "answered_at")
    list_filter = ("is_correct",)


@admin.register(AssessmentResult)
class AssessmentResultAdmin(admin.ModelAdmin):
    list_display = ("id", "attempt", "score_points", "max_points", "percent", "correct_count", "graded_at")
    list_filter = ("graded_at",)


@admin.register(SecurityAlert)
class SecurityAlertAdmin(admin.ModelAdmin):
    list_display = ("id", "alert_type", "source", "webhook_delivered", "email_delivered", "created_at")
    list_filter = ("source", "alert_type", "created_at")
    readonly_fields = ("fingerprint", "payload", "mitigation", "webhook_delivered", "email_delivered", "created_at")
    search_fields = ("fingerprint", "alert_type")


@admin.register(GovernanceEvent)
class GovernanceEventAdmin(admin.ModelAdmin):
    """
    IMMUTABLE AUDIT LOG — read-only in admin.
    All fields are readonly. No add, change, or delete allowed.
    """

    list_display = (
        "id",
        "event_type",
        "entity_type",
        "entity_id",
        "actor_email",
        "correlation_id_short",
        "occurred_at",
    )
    list_filter = ("event_type", "entity_type", "occurred_at")
    search_fields = ("actor_email", "entity_type", "event_type", "correlation_id")
    ordering = ("-occurred_at", "-id")
    date_hierarchy = "occurred_at"

    readonly_fields = (
        "event_type",
        "entity_type",
        "entity_id",
        "actor",
        "actor_email",
        "payload",
        "correlation_id",
        "occurred_at",
    )

    def correlation_id_short(self, obj):
        cid = obj.correlation_id or ""
        return cid[:16] + "…" if len(cid) > 16 else cid or "—"

    correlation_id_short.short_description = "Correlation"

    def has_add_permission(self, request):
        return False  # Events are emitted via emit_governance_event() only

    def has_change_permission(self, request, obj=None):
        return False  # Immutable

    def has_delete_permission(self, request, obj=None):
        return False  # Permanent audit trail

