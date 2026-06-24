from django.db import migrations, models


def forwards_subject_and_access(apps, schema_editor):
    User = apps.get_model("users", "User")
    UserAccess = apps.get_model("access", "UserAccess")
    ClassroomMembership = apps.get_model("classes", "ClassroomMembership")

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

    for u in User.objects.all():
        role = str(getattr(u, "role", "") or "").strip().lower()
        legacy = str(getattr(u, "role", "") or "").strip().upper()
        if getattr(u, "subject", None):
            continue
        if role == "super_admin" or getattr(u, "is_superuser", False):
            continue
        if role in ("student",):
            continue
        dom = scope_to_domain(getattr(u, "scope", None) or [])
        if not dom and legacy in ("MATH_TEACHER", "MATH_ADMIN"):
            dom = "math"
        if not dom and legacy in ("ENGLISH_TEACHER", "ENGLISH_ADMIN"):
            dom = "english"
        if dom:
            u.subject = dom
            u.save(update_fields=["subject"])

    for u in User.objects.filter(role__in=["teacher", "admin"]):
        sj = getattr(u, "subject", None)
        if sj in ("math", "english"):
            UserAccess.objects.get_or_create(
                user_id=u.pk,
                subject=sj,
                classroom_id=None,
                defaults={"granted_by_id": u.pk},
            )

    class_map = {"MATH": "math", "ENGLISH": "english"}
    for m in ClassroomMembership.objects.all().select_related("classroom"):
        dom = class_map.get(getattr(m.classroom, "subject", None) or "")
        if not dom:
            continue
        UserAccess.objects.get_or_create(
            user_id=m.user_id,
            subject=dom,
            classroom_id=m.classroom_id,
            defaults={"granted_by_id": m.user_id},
        )


class Migration(migrations.Migration):

    dependencies = [
        ("access", "0009_user_access"),
        ("classes", "0001_initial"),
        ("users", "0010_role_scope_rbac"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="subject",
            field=models.CharField(
                blank=True,
                choices=[("math", "Math"), ("english", "English")],
                db_index=True,
                max_length=16,
                null=True,
            ),
        ),
        migrations.RunPython(forwards_subject_and_access, migrations.RunPython.noop),
    ]
