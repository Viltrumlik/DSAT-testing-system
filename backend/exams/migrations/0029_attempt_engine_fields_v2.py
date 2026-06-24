from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("exams", "0028_backfill_testattempt_status"),
    ]

    operations = [
        migrations.RemoveField(model_name="testattempt", name="status"),
        migrations.AddField(
            model_name="testattempt",
            name="current_state",
            field=models.CharField(
                choices=[
                    ("NOT_STARTED", "Not started"),
                    ("MODULE_1_ACTIVE", "Module 1 active"),
                    ("MODULE_1_SUBMITTED", "Module 1 submitted"),
                    ("MODULE_2_ACTIVE", "Module 2 active"),
                    ("MODULE_2_SUBMITTED", "Module 2 submitted"),
                    ("SCORING", "Scoring"),
                    ("COMPLETED", "Completed"),
                ],
                default="NOT_STARTED",
                max_length=24,
                db_index=True,
            ),
        ),
        migrations.AddField(
            model_name="testattempt",
            name="module_1_started_at",
            field=models.DateTimeField(null=True, blank=True, db_index=True),
        ),
        migrations.AddField(
            model_name="testattempt",
            name="module_1_submitted_at",
            field=models.DateTimeField(null=True, blank=True, db_index=True),
        ),
        migrations.AddField(
            model_name="testattempt",
            name="module_2_started_at",
            field=models.DateTimeField(null=True, blank=True, db_index=True),
        ),
        migrations.AddField(
            model_name="testattempt",
            name="module_2_submitted_at",
            field=models.DateTimeField(null=True, blank=True, db_index=True),
        ),
        migrations.AddField(
            model_name="testattempt",
            name="scoring_started_at",
            field=models.DateTimeField(null=True, blank=True, db_index=True),
        ),
        migrations.AddField(
            model_name="testattempt",
            name="completed_at",
            field=models.DateTimeField(null=True, blank=True, db_index=True),
        ),
        migrations.AddField(
            model_name="testattempt",
            name="version_number",
            field=models.PositiveIntegerField(default=0, db_index=True),
        ),
    ]

