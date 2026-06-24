from django.db import migrations


def fix_test_admin(apps, schema_editor):
    Role = apps.get_model("access", "Role")
    Permission = apps.get_model("access", "Permission")
    RolePermission = apps.get_model("access", "RolePermission")
    try:
        role = Role.objects.get(code="TEST_ADMIN")
    except Role.DoesNotExist:
        return
    va = Permission.objects.filter(codename="view_all_tests").first()
    if va:
        RolePermission.objects.filter(role=role, permission=va).delete()


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("access", "0003_rbac_roles_v2"),
    ]

    operations = [
        migrations.RunPython(fix_test_admin, noop),
    ]
