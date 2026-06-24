from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("assessments", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="assessmentattempt",
            name="abandoned_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="assessmentattempt",
            name="last_activity_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="assessmentattempt",
            name="question_order",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddIndex(
            model_name="assessmentattempt",
            index=models.Index(fields=["student", "status", "started_at"], name="assessment__student_status_started_idx"),
        ),
        migrations.AlterField(
            model_name="assessmentattempt",
            name="status",
            field=models.CharField(
                choices=[
                    ("in_progress", "In progress"),
                    ("submitted", "Submitted"),
                    ("graded", "Graded"),
                    ("abandoned", "Abandoned"),
                ],
                db_index=True,
                default="in_progress",
                max_length=24,
            ),
        ),
        migrations.RemoveConstraint(
            model_name="assessmentattempt",
            name="uniq_active_attempt_per_hw_student_status",
        ),
        migrations.AddConstraint(
            model_name="assessmentattempt",
            constraint=models.UniqueConstraint(
                fields=("homework", "student"),
                condition=models.Q(("status", "in_progress")),
                name="uniq_active_attempt_per_hw_student_in_progress",
            ),
        ),
        migrations.AddField(
            model_name="assessmentanswer",
            name="first_seen_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="assessmentanswer",
            name="last_seen_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
    ]

