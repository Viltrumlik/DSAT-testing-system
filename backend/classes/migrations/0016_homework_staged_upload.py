from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("classes", "0015_submissionfile_idempotency"),
    ]

    operations = [
        migrations.CreateModel(
            name="HomeworkStagedUpload",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("storage_path", models.CharField(max_length=512)),
                ("upload_token", models.CharField(blank=True, default="", max_length=64)),
                ("content_sha256", models.CharField(blank=True, default="", max_length=64)),
                (
                    "deterministic",
                    models.BooleanField(
                        default=False,
                        help_text="True when path was derived from a client upload_token (retry overwrites same key).",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[("staging", "Staging"), ("attached", "Attached"), ("abandoned", "Abandoned")],
                        db_index=True,
                        default="staging",
                        max_length=16,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "submission",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="staged_uploads",
                        to="classes.submission",
                    ),
                ),
            ],
            options={
                "db_table": "class_homework_staged_uploads",
                "ordering": ["-id"],
            },
        ),
        migrations.AddConstraint(
            model_name="homeworkstagedupload",
            constraint=models.UniqueConstraint(
                fields=("submission", "storage_path"),
                name="uniq_homework_staged_path_per_submission",
            ),
        ),
    ]
