"""
Replace TEACHER / ENGLISH_ADMIN / MATH_ADMIN with ENGLISH_TEACHER / MATH_TEACHER.

- New roles get admin-like LMS permissions (exams, mocks, classrooms, assign access)
  scoped to one subject via view_english_tests / view_math_tests + ABAC in code.
- Does NOT grant manage_users or manage_roles (true admins only).

Legacy TEACHER users are moved to MATH_TEACHER (reassign in admin if needed).
"""

from django.db import migrations


def forward(apps, schema_editor):
    Permission = apps.get_model("access", "Permission")
    Role = apps.get_model("access", "Role")
    RolePermission = apps.get_model("access", "RolePermission")
    User = apps.get_model("users", "User")

    definitions = [
        ("*", "All permissions"),
        ("manage_users", "Manage users"),
        ("manage_roles", "Manage roles and assignments"),
        ("access_lms_admin", "Access Next.js LMS admin panel"),
        ("create_test", "Create practice / pastpaper tests"),
        ("edit_test", "Edit practice tests and questions"),
        ("delete_test", "Delete practice tests"),
        ("view_all_tests", "View all practice tests"),
        ("assign_test_access", "Assign test access to students"),
        ("view_english_tests", "View English / R&W tests only"),
        ("view_math_tests", "View math tests only"),
        ("submit_test", "Take and submit tests"),
        ("manage_classrooms", "Manage site-wide groups / classrooms"),
        ("create_mock_sat", "Create full timed SAT mock exams"),
        ("create_midterm_mock", "Create midterm-style timed exams only"),
    ]
    perms = {}
    for codename, name in definitions:
        p, _ = Permission.objects.get_or_create(codename=codename, defaults={"name": name})
        if p.name != name:
            p.name = name
            p.save(update_fields=["name"])
        perms[codename] = p

    # Admin-like for LMS content, single-subject via view_* (ABAC in authorize()).
    english_teacher = [
        "submit_test",
        "access_lms_admin",
        "assign_test_access",
        "manage_classrooms",
        "create_midterm_mock",
        "create_mock_sat",
        "create_test",
        "edit_test",
        "delete_test",
        "view_english_tests",
    ]
    math_teacher = [
        "submit_test",
        "access_lms_admin",
        "assign_test_access",
        "manage_classrooms",
        "create_midterm_mock",
        "create_mock_sat",
        "create_test",
        "edit_test",
        "delete_test",
        "view_math_tests",
    ]

    def seed_role(code: str, name: str, plist: list[str]) -> None:
        role, _ = Role.objects.get_or_create(code=code, defaults={"name": name})
        if role.name != name:
            role.name = name
            role.save(update_fields=["name"])
        RolePermission.objects.filter(role=role).delete()
        for pc in plist:
            RolePermission.objects.create(role=role, permission=perms[pc])

    seed_role("ENGLISH_TEACHER", "English Teacher", english_teacher)
    seed_role("MATH_TEACHER", "Math Teacher", math_teacher)

    rehome = [
        ("ENGLISH_ADMIN", "ENGLISH_TEACHER"),
        ("MATH_ADMIN", "MATH_TEACHER"),
        ("TEACHER", "MATH_TEACHER"),
    ]
    for old_code, new_code in rehome:
        old_role = Role.objects.filter(code=old_code).first()
        new_role = Role.objects.filter(code=new_code).first()
        if old_role and new_role:
            # Older deployments may not have ``system_role`` fields on the User model.
            try:
                User._meta.get_field("system_role")
            except Exception:
                continue
            User.objects.filter(system_role_id=old_role.pk).update(system_role_id=new_role.pk)

    for obsolete in ("TEACHER", "ENGLISH_ADMIN", "MATH_ADMIN"):
        Role.objects.filter(code=obsolete).delete()


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("access", "0006_math_admin_classrooms_midterms"),
        ("users", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(forward, noop_reverse),
    ]
