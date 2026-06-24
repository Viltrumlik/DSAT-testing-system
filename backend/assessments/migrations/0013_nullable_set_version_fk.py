"""
Migration 0013 — Add nullable set_version FK to HomeworkAssignment and AssessmentAttempt.

GOVERNANCE / ROLLBACK SAFETY:
  - Both columns are nullable (null=True, blank=True, default=NULL).
  - Existing rows get NULL — backward compatible with old workers that don't know
    about this column. Old code paths fall back to live question lookup.
  - on_delete=PROTECT ensures a version with pinned assignments/attempts cannot
    be accidentally deleted (the delete guard on AssessmentSetVersion.delete()
    provides a second defence-in-depth layer).
  - This migration is safe to roll back: DROP COLUMN on nullable columns with no
    NOT NULL constraint is instantaneous on PostgreSQL (no table rewrite).

Phase 2 (future sprint): backfill set_version on historical rows, then add
NOT NULL constraint. NOT done here — nullable-first rollout.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("assessments", "0012_assessmentsetversion"),
    ]

    operations = [
        # HomeworkAssignment: pin the published version at assignment time.
        migrations.AddField(
            model_name="homeworkassignment",
            name="set_version",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="homework_assignments",
                to="assessments.assessmentsetversion",
            ),
        ),
        # AssessmentAttempt: carry the version from the homework into the attempt.
        migrations.AddField(
            model_name="assessmentattempt",
            name="set_version",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="attempts",
                to="assessments.assessmentsetversion",
            ),
        ),
    ]
