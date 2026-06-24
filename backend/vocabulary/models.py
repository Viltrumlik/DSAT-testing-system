from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class VocabularyWord(models.Model):
    PART_NOUN = "noun"
    PART_VERB = "verb"
    PART_ADJECTIVE = "adjective"
    PART_ADVERB = "adverb"
    PART_PRONOUN = "pronoun"
    PART_PREPOSITION = "preposition"
    PART_CONJUNCTION = "conjunction"
    PART_INTERJECTION = "interjection"
    PART_OTHER = "other"

    PART_CHOICES = (
        (PART_NOUN, "Noun"),
        (PART_VERB, "Verb"),
        (PART_ADJECTIVE, "Adjective"),
        (PART_ADVERB, "Adverb"),
        (PART_PRONOUN, "Pronoun"),
        (PART_PREPOSITION, "Preposition"),
        (PART_CONJUNCTION, "Conjunction"),
        (PART_INTERJECTION, "Interjection"),
        (PART_OTHER, "Other"),
    )

    DIFF_EASY = 1
    DIFF_MEDIUM = 2
    DIFF_HARD = 3

    word = models.CharField(max_length=120, db_index=True)
    meaning = models.TextField(blank=True, default="")
    example = models.TextField(blank=True, default="")
    part_of_speech = models.CharField(max_length=24, choices=PART_CHOICES, default=PART_OTHER)
    difficulty = models.PositiveSmallIntegerField(default=DIFF_MEDIUM, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "vocabulary_words"
        ordering = ["word", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["word", "meaning"],
                name="uniq_vocab_word_meaning",
            )
        ]

    def __str__(self) -> str:
        return self.word


class UserVocabularyProgress(models.Model):
    STATUS_NEW = "new"
    STATUS_LEARNING = "learning"
    STATUS_MASTERED = "mastered"

    STATUS_CHOICES = (
        (STATUS_NEW, "New"),
        (STATUS_LEARNING, "Learning"),
        (STATUS_MASTERED, "Mastered"),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="vocabulary_progress",
    )
    word = models.ForeignKey(
        VocabularyWord,
        on_delete=models.CASCADE,
        related_name="user_progress",
    )
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_NEW, db_index=True)
    correct_count = models.PositiveIntegerField(default=0)
    wrong_count = models.PositiveIntegerField(default=0)
    last_reviewed = models.DateTimeField(null=True, blank=True, db_index=True)

    # Scheduling (simple spaced repetition)
    interval_days = models.PositiveIntegerField(default=0)
    next_review_at = models.DateTimeField(null=True, blank=True, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        db_table = "vocabulary_user_progress"
        constraints = [
            models.UniqueConstraint(fields=["user", "word"], name="uniq_vocab_user_word"),
        ]
        indexes = [
            models.Index(fields=["user", "status", "next_review_at"]),
            models.Index(fields=["user", "next_review_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.word_id} ({self.status})"

    def mark_review(self, *, result: str, reviewed_at=None) -> None:
        """
        Basic scheduler:
        - wrong: reset interval, show again soon (minutes)
        - correct: grow interval (1, 2, 4, 7, 14, 30...) and promote status
        """
        reviewed_at = reviewed_at or timezone.now()
        self.last_reviewed = reviewed_at

        if result == "wrong":
            self.wrong_count = int(self.wrong_count or 0) + 1
            self.status = self.STATUS_LEARNING if self.status != self.STATUS_MASTERED else self.STATUS_LEARNING
            self.interval_days = 0
            self.next_review_at = reviewed_at + timezone.timedelta(minutes=10)
            return

        self.correct_count = int(self.correct_count or 0) + 1
        if self.status == self.STATUS_NEW:
            self.status = self.STATUS_LEARNING

        current = int(self.interval_days or 0)
        if current <= 0:
            next_days = 1
        elif current == 1:
            next_days = 2
        elif current == 2:
            next_days = 4
        elif current == 4:
            next_days = 7
        elif current == 7:
            next_days = 14
        elif current == 14:
            next_days = 30
        else:
            next_days = min(90, current + 30)

        self.interval_days = next_days
        self.next_review_at = reviewed_at + timezone.timedelta(days=next_days)

        # Mastery: simple threshold (tunable later)
        if self.correct_count >= 6 and self.wrong_count <= 3:
            self.status = self.STATUS_MASTERED


# ---------------------------------------------------------------------------
# Spaced repetition vocab (Word + definitions + SM-2-style progress)
# ---------------------------------------------------------------------------


class Word(models.Model):
    """
    Lexeme key: surface form + language code (e.g. en, ru).
    """

    text = models.CharField(max_length=200, db_index=True)
    language = models.CharField(max_length=16, db_index=True, default="en")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "vocab_words"
        ordering = ["language", "text", "id"]
        constraints = [
            models.UniqueConstraint(fields=["text", "language"], name="uniq_vocab_word_text_language"),
        ]

    def __str__(self) -> str:
        return f"{self.language}:{self.text}"


class WordDefinition(models.Model):
    word = models.ForeignKey(Word, on_delete=models.CASCADE, related_name="definitions")
    definition = models.TextField()
    example = models.TextField(blank=True, default="")
    order = models.PositiveSmallIntegerField(default=0, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "vocab_word_definitions"
        ordering = ["word_id", "order", "id"]


class UserWordProgress(models.Model):
    """
    One row per (user, Word). ``repetitions`` counts successful steps in the SM-2 loop;
    ``interval`` is the last scheduled interval in days (0 = learn / re-learn).
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="vocab_word_progress",
    )
    word = models.ForeignKey(Word, on_delete=models.CASCADE, related_name="user_progress_rows")
    ease_factor = models.FloatField(default=2.5)
    interval = models.PositiveIntegerField(default=0)
    repetitions = models.PositiveIntegerField(default=0)
    next_review_at = models.DateTimeField(null=True, blank=True, db_index=True)
    introduced_at = models.DateTimeField(null=True, blank=True)
    learning_phase = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        db_table = "vocab_user_word_progress"
        constraints = [
            models.UniqueConstraint(fields=["user", "word"], name="uniq_vocab_user_word_progress"),
        ]
        indexes = [
            models.Index(fields=["user", "next_review_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.word_id}"


class ReviewLog(models.Model):
    RESULT_AGAIN = "again"
    RESULT_HARD = "hard"
    RESULT_GOOD = "good"
    RESULT_EASY = "easy"
    RESULT_CHOICES = (
        (RESULT_AGAIN, "Again"),
        (RESULT_HARD, "Hard"),
        (RESULT_GOOD, "Good"),
        (RESULT_EASY, "Easy"),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="vocab_review_logs",
    )
    word = models.ForeignKey(Word, on_delete=models.CASCADE, related_name="review_logs")
    result = models.CharField(max_length=16, choices=RESULT_CHOICES, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "vocab_review_logs"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["user", "word", "created_at"]),
        ]


class UserVocabularyReviewEvent(models.Model):
    RESULT_CORRECT = "correct"
    RESULT_WRONG = "wrong"
    RESULT_CHOICES = ((RESULT_CORRECT, "Correct"), (RESULT_WRONG, "Wrong"))

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="vocabulary_review_events",
    )
    word = models.ForeignKey(
        VocabularyWord,
        on_delete=models.CASCADE,
        related_name="review_events",
    )
    result = models.CharField(max_length=16, choices=RESULT_CHOICES, db_index=True)
    reviewed_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        db_table = "vocabulary_review_events"
        indexes = [
            models.Index(fields=["user", "reviewed_at"]),
            models.Index(fields=["user", "result", "reviewed_at"]),
        ]

