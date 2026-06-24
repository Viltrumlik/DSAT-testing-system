"""
Migration 0012 — Create assessment_set_versions table.

GOVERNANCE:
  - Append-only table; no DELETE, no UPDATE after INSERT enforced at model layer.
  - Two unique constraints:
      (assessment_set, version_number)   — sequential versioning within a set
      (assessment_set, snapshot_checksum) — idempotency / no duplicate-content versions
  - FK to assessment_set uses PROTECT — cannot delete a set that has published versions.
  - FK to published_by (AUTH_USER_MODEL) uses PROTECT, nullable — NULL = system/backfill.

ROLLBACK SAFETY:
  - This migration is purely additive. No existing table is modified.
  - Rolling back drops the new table only; existing data is unaffected.
"""

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("assessments", "0011_deduplicate_homework_assignment_and_restore_classroom_set_uniq"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AssessmentSetVersion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "assessment_set",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="versions",
                        to="assessments.assessmentset",
                    ),
                ),
                ("version_number", models.PositiveIntegerField(db_index=True)),
                ("snapshot_json", models.JSONField()),
                ("snapshot_checksum", models.CharField(db_index=True, max_length=64)),
                ("question_count", models.PositiveIntegerField(default=0)),
                (
                    "published_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="published_assessment_versions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                ("published_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
            ],
            options={
                "db_table": "assessment_set_versions",
                "ordering": ["-published_at", "-version_number"],
            },
        ),
        migrations.AddConstraint(
            model_name="assessmentsetversion",
            constraint=models.UniqueConstraint(
                fields=["assessment_set", "version_number"],
                name="uniq_set_version_number",
            ),
        ),
        migrations.AddConstraint(
            model_name="assessmentsetversion",
            constraint=models.UniqueConstraint(
                fields=["assessment_set", "snapshot_checksum"],
                name="uniq_set_version_checksum",
            ),
        ),
        # No extra index operations: unique constraints create implicit indexes on their columns,
        # and published_at has db_index=True on the field definition.
    ]
