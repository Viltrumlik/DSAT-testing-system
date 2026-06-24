from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("exams", "0026_bulkassignmentdispatch_hardening"),
    ]

    operations = [
        migrations.AddField(
            model_name="testattempt",
            name="status",
            field=models.CharField(
                choices=[
                    ("NOT_STARTED", "Not started"),
                    ("MODULE_1_ACTIVE", "Module 1 active"),
                    ("MODULE_1_SUBMITTED", "Module 1 submitted"),
                    ("MODULE_2_ACTIVE", "Module 2 active"),
                    ("MODULE_2_SUBMITTED", "Module 2 submitted"),
                    ("COMPLETED", "Completed"),
                ],
                default="NOT_STARTED",
                max_length=24,
                db_index=True,
            ),
        ),
    ]

