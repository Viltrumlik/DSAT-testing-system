from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("classes", "0010_submission_files_review_schedule"),
        ("assessments", "0004_active_time_and_grading_status"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AssessmentHomeworkAuditEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event_type", models.CharField(choices=[("assigned", "Assigned")], db_index=True, max_length=40)),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="assessment_homework_audit_events",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "assessment_set",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="homework_audit_events",
                        to="assessments.assessmentset",
                    ),
                ),
                (
                    "classroom",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="assessment_homework_audit_events",
                        to="classes.classroom",
                    ),
                ),
                (
                    "homework",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="audit_events",
                        to="assessments.homeworkassignment",
                    ),
                ),
            ],
            options={
                "db_table": "assessment_homework_audit_events",
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.AddIndex(
            model_name="assessmenthomeworkauditevent",
            index=models.Index(fields=["classroom", "created_at"], name="assess_hw_a_classro_9a5a5d_idx"),
        ),
        migrations.AddIndex(
            model_name="assessmenthomeworkauditevent",
            index=models.Index(fields=["assessment_set", "created_at"], name="assess_hw_a_assessm_4f4e8b_idx"),
        ),
        migrations.AddIndex(
            model_name="assessmenthomeworkauditevent",
            index=models.Index(fields=["event_type", "created_at"], name="assess_hw_a_event_t_5c0d37_idx"),
        ),
    ]

