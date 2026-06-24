# Generated manually — sync global UserAccess for test_admin rows that have a domain subject.

from django.db import migrations


def forwards(apps, schema_editor):
    User = apps.get_model("users", "User")
    UserAccess = apps.get_model("access", "UserAccess")
    for u in User.objects.filter(role="test_admin").iterator():
        subj = getattr(u, "subject", None)
        if subj not in ("math", "english"):
            continue
        UserAccess.objects.get_or_create(
            user_id=u.pk,
            subject=subj,
            classroom_id=None,
            defaults={"granted_by_id": u.pk},
        )


def backwards(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0013_test_admin_clear_subject_scope"),
        ("access", "0009_user_access"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
