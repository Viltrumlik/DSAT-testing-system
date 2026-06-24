from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("classes", "0011_submission_reviewed_status_and_hardening"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="submission",
            name="return_note",
            field=models.TextField(blank=True, help_text="Visible to student when status is RETURNED."),
        ),
        migrations.AddField(
            model_name="submission",
            name="returned_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AlterField(
            model_name="submission",
            name="status",
            field=models.CharField(
                choices=[
                    ("DRAFT", "Draft"),
                    ("SUBMITTED", "Submitted"),
                    ("REVIEWED", "Reviewed"),
                    ("RETURNED", "Returned for revision"),
                ],
                db_index=True,
                default="DRAFT",
                max_length=16,
            ),
        ),
        migrations.CreateModel(
            name="SubmissionAuditEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event_type", models.CharField(db_index=True, max_length=40)),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="submission_audit_events",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "submission",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="audit_events",
                        to="classes.submission",
                    ),
                ),
            ],
            options={
                "db_table": "class_submission_audit_events",
                "ordering": ["-created_at", "-id"],
            },
        ),
    ]
