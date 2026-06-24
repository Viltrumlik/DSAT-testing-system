from django.db import migrations


def clear_test_admin_subject(apps, schema_editor):
    User = apps.get_model("users", "User")
    User.objects.filter(role="test_admin").exclude(subject__isnull=True).update(subject=None)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0012_user_teacher_admin_subject_check"),
    ]

    operations = [
        migrations.RunPython(clear_test_admin_subject, noop_reverse),
    ]
