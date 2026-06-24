import mimetypes
import os

from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings
from django.core.files import File
from django.utils import timezone


def _migrate_legacy(apps, schema_editor):
    Submission = apps.get_model("classes", "Submission")
    SubmissionFile = apps.get_model("classes", "SubmissionFile")
    SubmissionReview = apps.get_model("classes", "SubmissionReview")
    Grade = apps.get_model("classes", "Grade")

    for g in Grade.objects.all():
        SubmissionReview.objects.create(
            submission_id=g.submission_id,
            teacher_id=g.graded_by_id,
            grade=g.score,
            feedback=g.feedback or "",
            reviewed_at=g.graded_at or timezone.now(),
        )

    for sub in Submission.objects.all():
        uf = getattr(sub, "upload_file", None)
        if not uf:
            continue
        name = os.path.basename(uf.name)
        mt = (mimetypes.guess_type(name)[0] or "")[:120]
        sf = SubmissionFile(
            submission_id=sub.pk,
            file_name=name[:255],
            file_type=mt,
        )
        try:
            with uf.open("rb") as fh:
                sf.file.save(name, File(fh), save=True)
        except OSError:
            continue


def _noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("classes", "0009_backfill_classroom_stream"),
    ]

    operations = [
        migrations.AddField(
            model_name="classroom",
            name="schedule_summary",
            field=models.CharField(
                blank=True,
                default="Tuesday, Thursday, Saturday",
                help_text="Weekly meeting pattern shown on the class page (edit to match your center).",
                max_length=240,
            ),
        ),
        migrations.CreateModel(
            name="SubmissionFile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("file", models.FileField(upload_to="homework_submissions/%Y/%m/")),
                ("file_name", models.CharField(blank=True, max_length=255)),
                ("file_type", models.CharField(blank=True, max_length=120)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "submission",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="files",
                        to="classes.submission",
                    ),
                ),
            ],
            options={
                "db_table": "class_submission_files",
                "ordering": ["id"],
            },
        ),
        migrations.CreateModel(
            name="SubmissionReview",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("grade", models.DecimalField(blank=True, decimal_places=2, max_digits=6, null=True)),
                ("feedback", models.TextField(blank=True)),
                ("reviewed_at", models.DateTimeField(db_index=True, default=timezone.now)),
                (
                    "submission",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="review",
                        to="classes.submission",
                    ),
                ),
                (
                    "teacher",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="given_submission_reviews",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "class_submission_reviews",
            },
        ),
        migrations.RunPython(_migrate_legacy, _noop_reverse),
        migrations.RemoveField(
            model_name="submission",
            name="text_response",
        ),
        migrations.RemoveField(
            model_name="submission",
            name="upload_file",
        ),
        migrations.DeleteModel(
            name="Grade",
        ),
    ]
