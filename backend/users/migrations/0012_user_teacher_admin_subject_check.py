from django.db import migrations, models
from django.db.models import Q


def ensure_teacher_admin_subject(apps, schema_editor):
    User = apps.get_model("users", "User")

    def scope_to_domain(scope_list):
        if not scope_list:
            return None
        for s in scope_list:
            v = str(s).strip().lower()
            if v in ("math",):
                return "math"
            if v in ("english", "rw", "reading_writing", "reading-writing"):
                return "english"
        return None

    for u in User.objects.filter(role__in=["teacher", "admin"]):
        sj = getattr(u, "subject", None)
        if sj in ("math", "english"):
            continue
        dom = scope_to_domain(getattr(u, "scope", None) or [])
        if dom:
            u.subject = dom
            u.save(update_fields=["subject"])
            continue
        u.role = "student"
        u.subject = None
        u.save(update_fields=["role", "subject"])


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0011_user_subject_access_backfill"),
    ]

    operations = [
        migrations.RunPython(ensure_teacher_admin_subject, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="user",
            constraint=models.CheckConstraint(
                condition=~Q(role__in=["teacher", "admin"]) | Q(subject__in=["math", "english"]),
                name="users_teacher_admin_subject_required",
            ),
        ),
    ]
