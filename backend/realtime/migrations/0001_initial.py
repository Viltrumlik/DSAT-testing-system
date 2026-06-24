import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="RealtimeEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event_type", models.CharField(db_index=True, max_length=64)),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="realtime_events",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "realtime_events",
                "ordering": ["id"],
            },
        ),
        migrations.AddIndex(
            model_name="realtimeevent",
            index=models.Index(fields=["user", "id"], name="realtime_e_user_id_idx"),
        ),
        migrations.AddIndex(
            model_name="realtimeevent",
            index=models.Index(fields=["user", "created_at"], name="realtime_e_user_created_idx"),
        ),
    ]

