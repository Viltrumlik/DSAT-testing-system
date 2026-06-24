from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0016_global_rbac_clear_staff_subject"),
    ]

    operations = [
        migrations.CreateModel(
            name="RefreshSession",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("refresh_jti", models.CharField(db_index=True, max_length=64, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("last_seen_at", models.DateTimeField(auto_now=True, db_index=True)),
                ("ip", models.CharField(blank=True, default="", max_length=64)),
                ("user_agent", models.CharField(blank=True, default="", max_length=512)),
                ("revoked_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                (
                    "user",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="refresh_sessions", to="users.user"),
                ),
            ],
            options={
                "db_table": "users_refresh_sessions",
            },
        ),
        migrations.AddIndex(
            model_name="refreshsession",
            index=models.Index(fields=["user", "revoked_at", "-last_seen_at"], name="users_refr_user_id_6c2b1f_idx"),
        ),
    ]

