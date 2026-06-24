from django.db import migrations, models


def backfill_role_scope(apps, schema_editor):
    User = apps.get_model("users", "User")

    def set_user(u, role: str, scope: list[str]):
        u.role = role
        u.scope = scope
        u.save(update_fields=["role", "scope"])

    for u in User.objects.select_related("system_role").all():
        if u.is_superuser:
            set_user(u, "super_admin", ["math", "english"])
            continue

        # Prefer existing value if already set (e.g. created after code change)
        if isinstance(getattr(u, "role", None), str) and u.role:
            # ensure scope exists
            if getattr(u, "scope", None) is None:
                u.scope = []
                u.save(update_fields=["scope"])
            continue

        # Legacy role from access.Role codes (uppercase)
        legacy = None
        if u.system_role_id:
            try:
                legacy = u.system_role.code
            except Exception:
                legacy = None

        legacy = (legacy or "").strip().upper()
        if legacy == "SUPER_ADMIN":
            set_user(u, "super_admin", ["math", "english"])
        elif legacy == "ADMIN":
            set_user(u, "admin", ["math", "english"])
        elif legacy == "MATH_ADMIN":
            set_user(u, "admin", ["math"])
        elif legacy == "ENGLISH_ADMIN":
            set_user(u, "admin", ["english"])
        elif legacy in ("MATH_TEACHER",):
            set_user(u, "teacher", ["math"])
        elif legacy in ("ENGLISH_TEACHER",):
            set_user(u, "teacher", ["english"])
        elif legacy in ("TEACHER",):
            set_user(u, "teacher", ["math", "english"])
        elif legacy in ("TEST_ADMIN",):
            set_user(u, "test_admin", ["math", "english"])
        else:
            set_user(u, "student", [])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0009_examdateoption"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="role",
            field=models.CharField(db_index=True, default="student", max_length=30),
        ),
        migrations.AddField(
            model_name="user",
            name="scope",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.RunPython(backfill_role_scope, noop_reverse),
    ]

