# Generated manually for RBAC + DB-backed access

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("classes", "0001_initial"),
        ("access", "0008_ensure_teacher_assign_test_access"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="UserAccess",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("subject", models.CharField(choices=[("math", "Math"), ("english", "English")], db_index=True, max_length=16)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "classroom",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="access_grants",
                        to="classes.classroom",
                    ),
                ),
                (
                    "granted_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="access_grants_given",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="access_grants",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "access_user_access",
            },
        ),
        migrations.AddConstraint(
            model_name="useraccess",
            constraint=models.UniqueConstraint(
                fields=("user", "subject", "classroom"),
                name="access_user_access_unique_user_subject_classroom",
            ),
        ),
    ]
