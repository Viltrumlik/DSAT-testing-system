# TEST_ADMIN: full test library + delete tests (no user management).

from django.db import migrations


def grant_test_admin_library(apps, schema_editor):
    Role = apps.get_model("access", "Role")
    Permission = apps.get_model("access", "Permission")
    RolePermission = apps.get_model("access", "RolePermission")

    role = Role.objects.filter(code="TEST_ADMIN").first()
    if not role:
        return
    for codename in ("view_all_tests", "delete_test"):
        p = Permission.objects.filter(codename=codename).first()
        if p:
            RolePermission.objects.get_or_create(role=role, permission=p)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("access", "0004_test_admin_drop_view_all_mocks"),
    ]

    operations = [
        migrations.RunPython(grant_test_admin_library, noop_reverse),
    ]
