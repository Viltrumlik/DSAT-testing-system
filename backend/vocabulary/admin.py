from django.contrib import admin

from .models import (
    ReviewLog,
    Word,
    WordDefinition,
    UserWordProgress,
    UserVocabularyProgress,
    UserVocabularyReviewEvent,
    VocabularyWord,
)


@admin.register(VocabularyWord)
class VocabularyWordAdmin(admin.ModelAdmin):
    list_display = ("id", "word", "part_of_speech", "difficulty", "created_at")
    search_fields = ("word", "meaning", "example")
    list_filter = ("part_of_speech", "difficulty", "created_at")


@admin.register(UserVocabularyProgress)
class UserVocabularyProgressAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "word",
        "status",
        "correct_count",
        "wrong_count",
        "interval_days",
        "next_review_at",
        "last_reviewed",
    )
    search_fields = ("user__email", "user__username", "word__word")
    list_filter = ("status", "next_review_at", "last_reviewed")


@admin.register(UserVocabularyReviewEvent)
class UserVocabularyReviewEventAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "word", "result", "reviewed_at")
    search_fields = ("user__email", "user__username", "word__word")
    list_filter = ("result", "reviewed_at")


class WordDefinitionInline(admin.TabularInline):
    model = WordDefinition
    extra = 0


@admin.register(Word)
class WordAdmin(admin.ModelAdmin):
    list_display = ("id", "text", "language", "created_at")
    search_fields = ("text",)
    list_filter = ("language",)
    inlines = [WordDefinitionInline]


@admin.register(UserWordProgress)
class UserWordProgressAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "word",
        "ease_factor",
        "interval",
        "repetitions",
        "next_review_at",
        "introduced_at",
        "learning_phase",
        "updated_at",
    )
    search_fields = ("user__email", "word__text")
    list_filter = ("next_review_at",)


@admin.register(ReviewLog)
class VocabReviewLogAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "word", "result", "created_at")
    search_fields = ("user__email", "word__text")
    list_filter = ("result",)

