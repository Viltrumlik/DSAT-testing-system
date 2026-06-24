from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("realtime", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="realtimeevent",
            name="dedupe_key",
            field=models.CharField(blank=True, db_index=True, max_length=64),
        ),
        migrations.AddIndex(
            model_name="realtimeevent",
            index=models.Index(fields=["user", "dedupe_key", "created_at"], name="rt_user_dedupe_created"),
        ),
    ]

