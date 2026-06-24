from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("classes", "0012_submission_returned_audit"),
    ]

    operations = [
        migrations.CreateModel(
            name="StaleStorageBlob",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("storage_name", models.CharField(db_index=True, max_length=512)),
                ("reason", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
            options={
                "db_table": "class_stale_storage_blobs",
                "ordering": ["-created_at"],
            },
        ),
    ]
