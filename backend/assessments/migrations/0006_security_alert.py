from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("assessments", "0005_homework_audit_and_assign_throttle"),
    ]

    operations = [
        migrations.CreateModel(
            name="SecurityAlert",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("alert_type", models.CharField(db_index=True, max_length=80)),
                ("source", models.CharField(db_index=True, default="homework_abuse", max_length=40)),
                ("fingerprint", models.CharField(blank=True, db_index=True, default="", max_length=512)),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("mitigation", models.JSONField(blank=True, null=True)),
                ("webhook_delivered", models.BooleanField(default=False)),
                ("email_delivered", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
            options={
                "db_table": "assessment_security_alerts",
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.AddIndex(
            model_name="securityalert",
            index=models.Index(fields=["alert_type", "created_at"], name="assess_sec_alert_type_created_idx"),
        ),
        migrations.AddIndex(
            model_name="securityalert",
            index=models.Index(fields=["source", "created_at"], name="assess_sec_alert_source_created_idx"),
        ),
    ]
