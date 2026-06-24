"""Ensure subject teachers keep assign_test_access (bulk assign / user list API)."""

from django.db import migrations


def forward(apps, schema_editor):
    Permission = apps.get_model("access", "Permission")
    Role = apps.get_model("access", "Role")
    RolePermission = apps.get_model("access", "RolePermission")

    p = Permission.objects.filter(codename="assign_test_access").first()
    if not p:
        return
    for code in ("ENGLISH_TEACHER", "MATH_TEACHER"):
        role = Role.objects.filter(code=code).first()
        if role:
            RolePermission.objects.get_or_create(role=role, permission=p)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("access", "0007_english_math_teacher_roles"),
    ]

    operations = [
        migrations.RunPython(forward, noop_reverse),
    ]
