from django.db import migrations


def sync_staff_flags(apps, schema_editor):
    User = apps.get_model("users", "User")
    Role = apps.get_model("access", "Role")
    try:
        super_role = Role.objects.get(code="SUPER_ADMIN")
    except Role.DoesNotExist:
        return
    for u in User.objects.all().only("id", "is_superuser", "system_role_id"):
        if getattr(u, "is_superuser", False):
            User.objects.filter(pk=u.pk).update(is_staff=True)
        elif u.system_role_id == super_role.id:
            User.objects.filter(pk=u.pk).update(is_staff=True)
        else:
            User.objects.filter(pk=u.pk).update(is_staff=False)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0005_system_role_rbac"),
        ("access", "0003_rbac_roles_v2"),
    ]

    operations = [
        migrations.RunPython(sync_staff_flags, noop),
    ]
