from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("assessments", "0003_audit_events_and_async_support"),
    ]

    operations = [
        migrations.AddField(
            model_name="assessmentattempt",
            name="active_time_seconds",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="assessmentattempt",
            name="grading_attempts",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="assessmentattempt",
            name="grading_error",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="assessmentattempt",
            name="grading_last_attempt_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="assessmentattempt",
            name="grading_status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("processing", "Processing"),
                    ("completed", "Completed"),
                    ("failed", "Failed"),
                ],
                db_index=True,
                default="pending",
                max_length=24,
            ),
        ),
    ]

