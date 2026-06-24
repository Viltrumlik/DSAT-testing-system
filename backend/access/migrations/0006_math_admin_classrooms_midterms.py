# Math admin: same portal + classroom capability as Teacher, without splitting roles.

from django.db import migrations


def upgrade_math_admin_role(apps, schema_editor):
    Permission = apps.get_model("access", "Permission")
    Role = apps.get_model("access", "Role")
    RolePermission = apps.get_model("access", "RolePermission")

    role = Role.objects.filter(code="MATH_ADMIN").first()
    if not role:
        return

    for codename, name in (
        ("access_lms_admin", "Access Next.js LMS admin panel"),
        ("manage_classrooms", "Manage site-wide groups / classrooms"),
        ("create_midterm_mock", "Create midterm-style timed exams only"),
    ):
        p, _ = Permission.objects.get_or_create(codename=codename, defaults={"name": name})
        if p.name != name:
            p.name = name
            p.save(update_fields=["name"])
        RolePermission.objects.get_or_create(role=role, permission=p)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("access", "0005_test_admin_library_perms"),
    ]

    operations = [
        migrations.RunPython(upgrade_math_admin_role, noop_reverse),
    ]
