from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("exams", "0035_testattempt_abandoned_checkpoint_state"),
    ]

    operations = [
        migrations.CreateModel(
            name="AttemptEngineAudit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("event", models.CharField(db_index=True, max_length=64)),
                ("from_state", models.CharField(blank=True, max_length=64)),
                ("to_state", models.CharField(max_length=64)),
                ("version_number", models.PositiveIntegerField(default=0)),
                ("detail", models.TextField(blank=True)),
                (
                    "attempt",
                    models.ForeignKey(
                        on_delete=models.CASCADE,
                        related_name="engine_audits",
                        to="exams.testattempt",
                    ),
                ),
            ],
            options={
                "db_table": "exams_attempt_engine_audit",
            },
        ),
        migrations.AddIndex(
            model_name="attemptengineaudit",
            index=models.Index(fields=["attempt", "created_at"], name="exams_audit_att_cre"),
        ),
    ]
