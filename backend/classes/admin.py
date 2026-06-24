from django.contrib import admin

from .models import (
    Classroom,
    ClassroomMembership,
    ClassPost,
    Assignment,
    Submission,
    SubmissionFile,
    SubmissionReview,
    SubmissionAuditEvent,
    StaleStorageBlob,
    ClassroomStreamItem,
    ClassComment,
)


@admin.register(Classroom)
class ClassroomAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "subject", "lesson_days", "lesson_time", "room_number", "join_code", "is_active", "created_at")
    search_fields = ("name", "subject", "lesson_time", "room_number", "join_code")
    list_filter = ("is_active", "created_at")


@admin.register(ClassroomMembership)
class ClassroomMembershipAdmin(admin.ModelAdmin):
    list_display = ("id", "classroom", "user", "role", "joined_at")
    search_fields = ("classroom__name", "user__email", "user__username")
    list_filter = ("role", "joined_at")


@admin.register(ClassPost)
class ClassPostAdmin(admin.ModelAdmin):
    list_display = ("id", "classroom", "author", "created_at")
    search_fields = ("classroom__name", "author__email")
    list_filter = ("created_at",)


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ("id", "classroom", "title", "due_at", "created_at")
    search_fields = ("title", "classroom__name")
    list_filter = ("created_at",)


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ("id", "assignment", "student", "status", "submitted_at", "updated_at")
    search_fields = ("assignment__title", "student__email")
    list_filter = ("status", "submitted_at")


@admin.register(SubmissionFile)
class SubmissionFileAdmin(admin.ModelAdmin):
    list_display = ("id", "submission", "file_name", "created_at")
    search_fields = ("file_name", "submission__assignment__title", "submission__student__email")


@admin.register(SubmissionReview)
class SubmissionReviewAdmin(admin.ModelAdmin):
    list_display = ("id", "submission", "teacher", "grade", "reviewed_at")
    search_fields = ("submission__assignment__title", "submission__student__email", "teacher__email")
    list_filter = ("reviewed_at",)


@admin.register(StaleStorageBlob)
class StaleStorageBlobAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "storage_name",
        "retry_count",
        "consecutive_failures",
        "last_attempt_at",
        "created_at",
    )
    search_fields = ("storage_name", "reason", "last_error")
    readonly_fields = (
        "storage_name",
        "reason",
        "retry_count",
        "consecutive_failures",
        "last_error",
        "last_attempt_at",
        "alert_logged_at",
        "created_at",
    )
    ordering = ("-created_at",)


@admin.register(SubmissionAuditEvent)
class SubmissionAuditEventAdmin(admin.ModelAdmin):
    list_display = ("id", "submission", "event_type", "actor", "created_at")
    list_filter = ("event_type", "created_at")
    search_fields = ("submission__assignment__title", "submission__student__email")
    readonly_fields = ("submission", "actor", "event_type", "payload", "created_at")
    ordering = ("-created_at",)


@admin.register(ClassroomStreamItem)
class ClassroomStreamItemAdmin(admin.ModelAdmin):
    list_display = ("id", "classroom", "stream_type", "related_id", "actor", "created_at")
    list_filter = ("stream_type", "created_at")
    search_fields = ("classroom__name",)


@admin.register(ClassComment)
class ClassCommentAdmin(admin.ModelAdmin):
    list_display = ("id", "classroom", "target_type", "target_id", "author", "created_at")
    list_filter = ("target_type", "created_at")
    search_fields = ("content", "author__email", "classroom__name")

