from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("exams", "0025_bulkassignmentdispatch"),
    ]

    operations = [
        migrations.AlterField(
            model_name="bulkassignmentdispatch",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("processing", "Processing"),
                    ("delivered", "Delivered"),
                    ("completed", "Completed"),
                    ("failed", "Failed"),
                ],
                db_index=True,
                default="pending",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="bulkassignmentdispatch",
            name="actor_snapshot",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="bulkassignmentdispatch",
            name="idempotency_key",
            field=models.CharField(blank=True, db_index=True, max_length=64),
        ),
        migrations.AddField(
            model_name="bulkassignmentdispatch",
            name="idempotency_expires_at",
            field=models.DateTimeField(blank=True, null=True, db_index=True),
        ),
    ]

