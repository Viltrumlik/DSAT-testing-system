from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("exams", "0030_backfill_attempt_engine_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="AttemptIdempotencyKey",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("endpoint", models.CharField(max_length=64, db_index=True)),
                ("key", models.CharField(max_length=128, db_index=True)),
                ("response_status", models.PositiveSmallIntegerField(default=200)),
                ("response_json", models.JSONField(default=dict, blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("expires_at", models.DateTimeField(null=True, blank=True, db_index=True)),
                (
                    "attempt",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="idempotency_keys",
                        to="exams.testattempt",
                    ),
                ),
            ],
            options={
                "db_table": "exams_attempt_idempotency_keys",
            },
        ),
        migrations.AddConstraint(
            model_name="attemptidempotencykey",
            constraint=models.UniqueConstraint(fields=("attempt", "endpoint", "key"), name="uniq_attempt_endpoint_key"),
        ),
    ]

