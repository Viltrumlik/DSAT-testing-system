# Generated manually — expanded roles, LMS admin vs Django admin, mock SAT vs midterm.

from django.db import migrations


def seed_rbac_v2(apps, schema_editor):
    Permission = apps.get_model("access", "Permission")
    Role = apps.get_model("access", "Role")
    RolePermission = apps.get_model("access", "RolePermission")

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

    student = [
        "submit_test",
    ]
    teacher = [
        "submit_test",
        "access_lms_admin",
        "assign_test_access",
        "manage_classrooms",
        "create_midterm_mock",
        "edit_test",
    ]
    # Pastpaper authoring only; view_all_tests would widen mock-exam lists incorrectly.
    test_admin = [
        "submit_test",
        "access_lms_admin",
        "create_test",
        "edit_test",
        "delete_test",
        "view_all_tests",
    ]
    admin = [
        "submit_test",
        "access_lms_admin",
        "manage_users",
        "manage_roles",
        "assign_test_access",
        "manage_classrooms",
        "view_all_tests",
        "view_english_tests",
        "view_math_tests",
        "create_test",
        "edit_test",
        "delete_test",
        "create_mock_sat",
        "create_midterm_mock",
    ]
    english_admin = [
        "submit_test",
        "access_lms_admin",
        "view_english_tests",
        "create_test",
        "edit_test",
        "assign_test_access",
    ]
    math_admin = [
        "submit_test",
        "access_lms_admin",
        "assign_test_access",
        "manage_classrooms",
        "create_midterm_mock",
        "view_math_tests",
        "create_test",
        "edit_test",
    ]

    roles_cfg = [
        ("SUPER_ADMIN", "Super Admin", ["*"]),
        ("ADMIN", "Admin", admin),
        ("TEACHER", "Teacher", teacher),
        ("TEST_ADMIN", "Test Admin", test_admin),
        ("ENGLISH_ADMIN", "English Admin", english_admin),
        ("MATH_ADMIN", "Math Admin", math_admin),
        ("STUDENT", "Student", student),
    ]
    for code, name, plist in roles_cfg:
        role, _ = Role.objects.get_or_create(code=code, defaults={"name": name})
        if role.name != name:
            role.name = name
            role.save(update_fields=["name"])
        RolePermission.objects.filter(role=role).delete()
        for pc in plist:
            RolePermission.objects.create(role=role, permission=perms[pc])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("access", "0002_seed_rbac"),
    ]

    operations = [
        migrations.RunPython(seed_rbac_v2, noop_reverse),
    ]
