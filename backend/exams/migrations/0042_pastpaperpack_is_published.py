"""
Migration: add is_published + published_at to PastpaperPack.

Backfills all pre-existing packs to is_published=True so that currently
assigned packs remain visible to students after the publish gate is added.
New packs created after this migration start as is_published=False and
require an explicit publish action.
"""

from django.db import migrations, models
from django.utils import timezone


def backfill_existing_packs(apps, schema_editor):
    PastpaperPack = apps.get_model("exams", "PastpaperPack")
    PastpaperPack.objects.all().update(is_published=True, published_at=timezone.now())


class Migration(migrations.Migration):

    dependencies = [
        ("exams", "0041_testattempt_mock_exam_fk"),
    ]

    operations = [
        migrations.AddField(
            model_name="pastpaperpack",
            name="is_published",
            field=models.BooleanField(
                default=False,
                db_index=True,
                help_text=(
                    "Only published packs are shown to students. "
                    "A pack must be structurally valid (sat_violations empty) before publishing."
                ),
            ),
        ),
        migrations.AddField(
            model_name="pastpaperpack",
            name="published_at",
            field=models.DateTimeField(null=True, blank=True),
        ),
        # Backfill: all existing packs become published so no student access is lost.
        migrations.RunPython(backfill_existing_packs, migrations.RunPython.noop),
    ]
