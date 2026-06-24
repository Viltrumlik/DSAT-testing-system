# Generated manually — normalize pre-unification role strings stored on User.role.

from django.db import migrations


def forwards(apps, schema_editor):
    User = apps.get_model("users", "User")
    for old, new in (
        ("math_teacher", "teacher"),
        ("english_teacher", "teacher"),
        ("math_admin", "admin"),
        ("english_admin", "admin"),
    ):
        User.objects.filter(role__iexact=old).update(role=new)


def backwards(apps, schema_editor):
    # Lossy forward migration; no safe reverse without storing previous values.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0014_test_admin_useraccess_backfill"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
