from __future__ import annotations

from rest_framework import serializers

from .models import VocabularyWord, UserVocabularyProgress


class VocabularyWordSerializer(serializers.ModelSerializer):
    class Meta:
        model = VocabularyWord
        fields = [
            "id",
            "word",
            "meaning",
            "example",
            "part_of_speech",
            "difficulty",
            "created_at",
        ]


class VocabularyWordAdminWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = VocabularyWord
        fields = [
            "id",
            "word",
            "meaning",
            "example",
            "part_of_speech",
            "difficulty",
            "created_at",
        ]
        read_only_fields = ["created_at"]


class UserVocabularyProgressSerializer(serializers.ModelSerializer):
    word = VocabularyWordSerializer(read_only=True)

    class Meta:
        model = UserVocabularyProgress
        fields = [
            "id",
            "word",
            "status",
            "correct_count",
            "wrong_count",
            "last_reviewed",
            "interval_days",
            "next_review_at",
        ]


class VocabularyReviewSerializer(serializers.Serializer):
    word_id = serializers.IntegerField()
    result = serializers.ChoiceField(choices=["correct", "wrong"])

