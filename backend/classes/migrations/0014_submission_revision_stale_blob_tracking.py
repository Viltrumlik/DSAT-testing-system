from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("classes", "0013_stale_storage_blob"),
    ]

    operations = [
        migrations.AddField(
            model_name="submission",
            name="revision",
            field=models.PositiveIntegerField(db_index=True, default=0),
        ),
        migrations.AddField(
            model_name="stalestorageblob",
            name="alert_logged_at",
            field=models.DateTimeField(blank=True, help_text="When we emitted a CRITICAL log for this row (repeated delete failures).", null=True),
        ),
        migrations.AddField(
            model_name="stalestorageblob",
            name="consecutive_failures",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="stalestorageblob",
            name="last_attempt_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="stalestorageblob",
            name="last_error",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="stalestorageblob",
            name="retry_count",
            field=models.PositiveIntegerField(default=0),
        ),
    ]
