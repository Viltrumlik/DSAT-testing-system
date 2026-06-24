from django.contrib import admin

from .models import (
    BankDomain,
    BankPassage,
    BankQuestion,
    BankQuestionVersion,
    BankSkill,
    ImportBatch,
    QbIdCounter,
)


class BankSkillInline(admin.TabularInline):
    model = BankSkill
    extra = 0


@admin.register(BankDomain)
class BankDomainAdmin(admin.ModelAdmin):
    list_display = ("name", "subject", "code", "display_order")
    list_filter = ("subject",)
    search_fields = ("name", "code")
    inlines = [BankSkillInline]


@admin.register(BankSkill)
class BankSkillAdmin(admin.ModelAdmin):
    list_display = ("name", "domain", "code", "display_order")
    list_filter = ("domain__subject",)
    search_fields = ("name", "code")


@admin.register(ImportBatch)
class ImportBatchAdmin(admin.ModelAdmin):
    list_display = ("id", "source_type", "filename", "status", "total_candidates", "promoted_count", "created_at")
    list_filter = ("source_type", "status")
    search_fields = ("filename", "source_reference")


@admin.register(BankPassage)
class BankPassageAdmin(admin.ModelAdmin):
    list_display = ("id", "subject", "source_type", "created_at")
    list_filter = ("subject", "source_type")
    search_fields = ("passage_text", "content_hash")


@admin.register(BankQuestion)
class BankQuestionAdmin(admin.ModelAdmin):
    list_display = ("qb_id", "subject", "status", "domain", "skill", "difficulty", "question_type", "created_at")
    list_filter = ("subject", "status", "difficulty", "question_type", "source_type")
    search_fields = ("qb_id", "question_text", "content_hash", "source_reference")
    readonly_fields = ("qb_id", "content_hash", "current_version", "created_at", "updated_at")
    autocomplete_fields = ("domain", "skill", "passage")


@admin.register(BankQuestionVersion)
class BankQuestionVersionAdmin(admin.ModelAdmin):
    list_display = ("bank_question", "version_number", "snapshot_checksum", "created_at")
    search_fields = ("bank_question__qb_id", "snapshot_checksum")
    # Immutable records: view-only in admin.
    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(QbIdCounter)
class QbIdCounterAdmin(admin.ModelAdmin):
    list_display = ("subject", "last_value")
