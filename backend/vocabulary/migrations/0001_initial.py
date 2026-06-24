from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="VocabularyWord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("word", models.CharField(db_index=True, max_length=120)),
                ("meaning", models.TextField(blank=True, default="")),
                ("example", models.TextField(blank=True, default="")),
                (
                    "part_of_speech",
                    models.CharField(
                        choices=[
                            ("noun", "Noun"),
                            ("verb", "Verb"),
                            ("adjective", "Adjective"),
                            ("adverb", "Adverb"),
                            ("pronoun", "Pronoun"),
                            ("preposition", "Preposition"),
                            ("conjunction", "Conjunction"),
                            ("interjection", "Interjection"),
                            ("other", "Other"),
                        ],
                        default="other",
                        max_length=24,
                    ),
                ),
                ("difficulty", models.PositiveSmallIntegerField(db_index=True, default=2)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
            options={
                "db_table": "vocabulary_words",
                "ordering": ["word", "id"],
            },
        ),
        migrations.AddConstraint(
            model_name="vocabularyword",
            constraint=models.UniqueConstraint(fields=("word", "meaning"), name="uniq_vocab_word_meaning"),
        ),
        migrations.CreateModel(
            name="UserVocabularyProgress",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "status",
                    models.CharField(
                        choices=[("new", "New"), ("learning", "Learning"), ("mastered", "Mastered")],
                        db_index=True,
                        default="new",
                        max_length=16,
                    ),
                ),
                ("correct_count", models.PositiveIntegerField(default=0)),
                ("wrong_count", models.PositiveIntegerField(default=0)),
                ("last_reviewed", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("interval_days", models.PositiveIntegerField(default=0)),
                ("next_review_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True, db_index=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="vocabulary_progress",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "word",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="user_progress",
                        to="vocabulary.vocabularyword",
                    ),
                ),
            ],
            options={
                "db_table": "vocabulary_user_progress",
            },
        ),
        migrations.AddIndex(
            model_name="uservocabularyprogress",
            index=models.Index(fields=["user", "status", "next_review_at"], name="vocab_user__status_3cdb1d_idx"),
        ),
        migrations.AddIndex(
            model_name="uservocabularyprogress",
            index=models.Index(fields=["user", "next_review_at"], name="vocab_user__next_re_7cfd08_idx"),
        ),
        migrations.AddConstraint(
            model_name="uservocabularyprogress",
            constraint=models.UniqueConstraint(fields=("user", "word"), name="uniq_vocab_user_word"),
        ),
        migrations.CreateModel(
            name="UserVocabularyReviewEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "result",
                    models.CharField(
                        choices=[("correct", "Correct"), ("wrong", "Wrong")],
                        db_index=True,
                        max_length=16,
                    ),
                ),
                ("reviewed_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="vocabulary_review_events",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "word",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="review_events",
                        to="vocabulary.vocabularyword",
                    ),
                ),
            ],
            options={
                "db_table": "vocabulary_review_events",
            },
        ),
        migrations.AddIndex(
            model_name="uservocabularyreviewevent",
            index=models.Index(fields=["user", "reviewed_at"], name="vocab_event_user_id_4df692_idx"),
        ),
        migrations.AddIndex(
            model_name="uservocabularyreviewevent",
            index=models.Index(fields=["user", "result", "reviewed_at"], name="vocab_event_user_id_6a9a7e_idx"),
        ),
    ]

