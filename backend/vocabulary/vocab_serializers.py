from __future__ import annotations

from rest_framework import serializers

from .models import Word, WordDefinition, UserWordProgress, ReviewLog


class WordDefinitionSerializer(serializers.ModelSerializer):
    class Meta:
        model = WordDefinition
        fields = ["id", "definition", "example", "order", "created_at"]


class WordSerializer(serializers.ModelSerializer):
    definitions = WordDefinitionSerializer(many=True, read_only=True)

    class Meta:
        model = Word
        fields = ["id", "text", "language", "created_at", "definitions"]


class UserWordProgressBriefSerializer(serializers.ModelSerializer):
    """Scheduling fields without nesting ``word`` (pair with sibling ``word`` in API payloads)."""

    class Meta:
        model = UserWordProgress
        fields = [
            "id",
            "word_id",
            "ease_factor",
            "interval",
            "repetitions",
            "next_review_at",
            "introduced_at",
            "learning_phase",
            "created_at",
            "updated_at",
        ]


class UserWordProgressDetailSerializer(serializers.ModelSerializer):
    word = WordSerializer(read_only=True)

    class Meta:
        model = UserWordProgress
        fields = [
            "id",
            "word",
            "ease_factor",
            "interval",
            "repetitions",
            "next_review_at",
            "introduced_at",
            "learning_phase",
            "created_at",
            "updated_at",
        ]


class VocabReviewRequestSerializer(serializers.Serializer):
    word_id = serializers.IntegerField(min_value=1)
    result = serializers.ChoiceField(choices=[c[0] for c in ReviewLog.RESULT_CHOICES])
