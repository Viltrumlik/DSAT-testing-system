from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("assessments", "0002_attempt_state_machine_and_secure_time"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AssessmentAttemptAuditEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "event_type",
                    models.CharField(
                        choices=[
                            ("started", "Started"),
                            ("answer_saved", "Answer saved"),
                            ("submitted", "Submitted"),
                            ("graded", "Graded"),
                            ("abandoned", "Abandoned"),
                            ("timeout_abandoned", "Timeout abandoned"),
                        ],
                        db_index=True,
                        max_length=40,
                    ),
                ),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="assessment_audit_events",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "attempt",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="audit_events",
                        to="assessments.assessmentattempt",
                    ),
                ),
            ],
            options={
                "db_table": "assessment_attempt_audit_events",
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.AddIndex(
            model_name="assessmentattemptauditevent",
            index=models.Index(fields=["attempt", "created_at"], name="assessment_audit_attempt_created_idx"),
        ),
        migrations.AddIndex(
            model_name="assessmentattemptauditevent",
            index=models.Index(fields=["event_type", "created_at"], name="assessment_audit_type_created_idx"),
        ),
    ]

