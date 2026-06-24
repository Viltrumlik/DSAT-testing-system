# admin / test_admin are global — clear legacy subject field.

from django.db import migrations


def forwards(apps, schema_editor):
    User = apps.get_model("users", "User")
    User.objects.filter(role__in=("admin", "test_admin")).update(subject=None)


def backwards(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0015_normalize_legacy_user_roles"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
