"""Authorization constants: RBAC + single subject domain + DB-backed access.

Subject vocabulary (platform ``MATH`` / ``READING_WRITING`` vs domain ``math`` / ``english``)
is defined and converted only in ``access.subject_mapping``.
"""

WILDCARD = "*"

# Canonical permission codenames (spec)
PERM_MANAGE_USERS = "manage_users"
PERM_ASSIGN_ACCESS = "assign_access"
PERM_CREATE_CLASSROOM = "create_classroom"
PERM_MANAGE_TESTS = "manage_tests"
PERM_VIEW_DASHBOARD = "view_dashboard"
PERM_SUBMIT_TEST = "submit_test"

# Semantic aliases (same DB codename — use helpers for *view* vs *edit* semantics):
#   can_edit_tests()  → authorize(..., PERM_EDIT_TESTS, subject=platform)
#   can_view_tests()  → edit OR assign_access in subject scope (no separate DB perm)
PERM_EDIT_TESTS = PERM_MANAGE_TESTS

ALL_PERMISSION_CODENAMES = (
    PERM_SUBMIT_TEST,
    PERM_MANAGE_USERS,
    PERM_ASSIGN_ACCESS,
    PERM_CREATE_CLASSROOM,
    PERM_MANAGE_TESTS,
    PERM_VIEW_DASHBOARD,
)

# ``authorize(..., subject=<platform>)`` MUST receive a valid platform subject for these
# (MATH / READING_WRITING), except super_admin / Django superuser (wildcard).
PERMISSIONS_REQUIRING_PLATFORM_SUBJECT = frozenset(
    {
        PERM_MANAGE_USERS,
        PERM_MANAGE_TESTS,
        PERM_ASSIGN_ACCESS,
        PERM_CREATE_CLASSROOM,
    }
)

# Overrides must never grant these to students (defense in depth vs. bad admin data).
PERMISSIONS_STUDENT_OVERRIDE_DENIED = PERMISSIONS_REQUIRING_PLATFORM_SUBJECT

# Domain subject stored on User.subject and UserAccess.subject (exactly one for staff).
DOMAIN_MATH = "math"
DOMAIN_ENGLISH = "english"
ALL_DOMAIN_SUBJECTS = (DOMAIN_MATH, DOMAIN_ENGLISH)

# Platform subject values stored in DB (PracticeTest.subject)
SUBJECT_ENGLISH_PLATFORM = "READING_WRITING"  # "English / R&W"
SUBJECT_MATH_PLATFORM = "MATH"

# Canonical RBAC roles (lowercase, per spec)
ROLE_SUPER_ADMIN = "super_admin"
ROLE_ADMIN = "admin"
ROLE_TEACHER = "teacher"
ROLE_TEST_ADMIN = "test_admin"
ROLE_STUDENT = "student"

CANONICAL_ROLES = frozenset(
    {
        ROLE_SUPER_ADMIN,
        ROLE_ADMIN,
        ROLE_TEACHER,
        ROLE_TEST_ADMIN,
        ROLE_STUDENT,
    }
)
