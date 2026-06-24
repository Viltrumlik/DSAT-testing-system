"""
Migration: add mock_exam FK to TestAttempt

Tracks which MockExam a section attempt belongs to. Used for:
  - R&W-before-Math ordering enforcement
  - Break enforcement (server-authoritative SAT_BREAK_SECONDS)
  - Aggregated exam-level scoring
"""

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("exams", "0040_rename_exams_audit_att_cre_exams_attem_attempt_8fe07f_idx_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="testattempt",
            name="mock_exam",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="section_attempts",
                to="exams.mockexam",
            ),
        ),
    ]
