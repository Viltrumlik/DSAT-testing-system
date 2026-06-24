from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.exceptions import ValidationError
from django.db import models


class ExamDateOption(models.Model):
    """Admin-defined SAT/exam dates students may choose from (profile dropdown)."""

    exam_date = models.DateField(unique=True, db_index=True)
    label = models.CharField(max_length=200, blank=True, default="")
    is_active = models.BooleanField(default=True, db_index=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "users_exam_date_option"
        ordering = ["sort_order", "exam_date"]

    def __str__(self):
        return self.label.strip() or str(self.exam_date)


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("The Email field must be set")
        email = self.normalize_email(email)
        role = extra_fields.pop("role", None)
        scope = extra_fields.pop("scope", None)
        subject = extra_fields.pop("subject", None)
        system_role = extra_fields.pop("system_role", None)  # legacy; kept for DB compatibility
        user = self.model(email=email, **extra_fields)
        # Canonical authorization fields (RBAC + scope)
        if isinstance(role, str) and role.strip():
            user.role = role.strip()
        if scope is not None:
            user.scope = scope
        if isinstance(subject, str) and subject.strip():
            user.subject = subject.strip().lower()
        # Do not derive role from system_role anymore; it is legacy.
        if system_role is not None:
            user.system_role = system_role
        user.set_password(password)
        from access import constants as auth_const

        eff_role = str(getattr(user, "role", "") or "").strip().lower()
        if eff_role == auth_const.ROLE_TEACHER:
            if getattr(user, "subject", None) not in auth_const.ALL_DOMAIN_SUBJECTS:
                raise ValueError("Teacher accounts require subject: math or english.")
        elif eff_role in (auth_const.ROLE_ADMIN, auth_const.ROLE_TEST_ADMIN):
            if getattr(user, "subject", None) not in (None, ""):
                raise ValueError("Admin and test_admin accounts must not have a subject set.")
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", "super_admin")
        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    username = models.CharField(max_length=150, unique=True, null=True, blank=True, db_index=True)
    email = models.EmailField(unique=True, db_index=True)
    system_role = models.ForeignKey(
        "access.Role",
        on_delete=models.PROTECT,
        related_name="users",
        null=True,
        blank=True,
    )
    is_frozen = models.BooleanField(default=False, db_index=True)
    # Canonical RBAC + scope fields
    role = models.CharField(max_length=30, default="student", db_index=True)
    scope = models.JSONField(
        default=list,
        blank=True,
        help_text="Legacy field; not used for authorization. Use ``User.subject`` and ``access.UserAccess``.",
    )
    subject = models.CharField(
        max_length=16,
        blank=True,
        null=True,
        db_index=True,
        choices=[("math", "Math"), ("english", "English")],
        help_text="Required for **teacher** (math or english). Must be null for admin, test_admin, super_admin, and students.",
    )
    profile_image = models.ImageField(upload_to='profiles/', null=True, blank=True)
    sat_exam_date = models.DateField(null=True, blank=True, help_text='Planned SAT exam date')
    target_score = models.PositiveIntegerField(null=True, blank=True, help_text='Target total SAT score (400–1600)')
    target_english = models.PositiveIntegerField(null=True, blank=True, help_text='Target English/Reading-Writing score (200–800)')
    target_math = models.PositiveIntegerField(null=True, blank=True, help_text='Target Math score (200–800)')
    phone_number = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        unique=True,
        db_index=True,
        help_text="E.164-style or local digits; optional, unique when set (e.g. for Telegram users).",
    )
    telegram_id = models.BigIntegerField(
        null=True,
        blank=True,
        unique=True,
        db_index=True,
        help_text="Telegram user id when linked or signed up via Telegram.",
    )
    last_password_change = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Set when the user changes password via API (adaptive security).",
    )
    # Until this time, step-up: valid JWTs are rejected (except allowlisted public/auth routes).
    security_step_up_required_until = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
    )

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []
    
    objects = UserManager()
    
    class Meta:
        db_table = "users"

    def __str__(self):
        return f"{self.email} ({self.role})"

    def clean(self):
        super().clean()
        from access import constants as auth_const

        role = str(getattr(self, "role", "") or "").strip().lower()
        raw_subj = getattr(self, "subject", None)
        subj = str(raw_subj).strip().lower() if raw_subj not in (None, "") else None

        if role == auth_const.ROLE_TEACHER:
            if subj not in auth_const.ALL_DOMAIN_SUBJECTS:
                raise ValidationError(
                    {"subject": "Teacher accounts require subject: math or english."}
                )
        elif role in (auth_const.ROLE_ADMIN, auth_const.ROLE_TEST_ADMIN):
            if subj is not None:
                raise ValidationError(
                    {"subject": "Admin and test_admin accounts must not have a subject set."}
                )
        elif role == auth_const.ROLE_SUPER_ADMIN:
            if subj is not None:
                raise ValidationError({"subject": "super_admin accounts must not have a subject set."})
        elif role == auth_const.ROLE_STUDENT:
            if subj is not None:
                raise ValidationError({"subject": "Student accounts must not have a subject set."})
        elif subj is not None:
            raise ValidationError({"subject": "Subject is not valid for this role."})

    @property
    def is_student(self):
        from access import constants

        return self.role == constants.ROLE_STUDENT

    @property
    def is_admin(self):
        """True if user has any LMS staff capability (permissions-based)."""
        from access.services import is_lms_staff_user

        return is_lms_staff_user(self)


class RefreshSession(models.Model):
    """
    Server-side session record for refresh token rotation + device list.
    One row per active refresh token (by jti).
    """

    user = models.ForeignKey("users.User", on_delete=models.CASCADE, related_name="refresh_sessions")
    refresh_jti = models.CharField(max_length=64, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    last_seen_at = models.DateTimeField(auto_now=True, db_index=True)
    ip = models.CharField(max_length=64, blank=True, default="")
    user_agent = models.CharField(max_length=512, blank=True, default="")
    revoked_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = "users_refresh_sessions"
        indexes = [
            models.Index(fields=["user", "revoked_at", "-last_seen_at"]),
        ]


class SecurityAuditEvent(models.Model):
    """
    Durable log for user-visible security events and operations automation.
    """

    SEVERITY_INFO = "info"
    SEVERITY_WARNING = "warning"
    SEVERITY_CRITICAL = "critical"

    user = models.ForeignKey("users.User", on_delete=models.CASCADE, related_name="security_audit_events")
    event_type = models.CharField(max_length=64, db_index=True)
    severity = models.CharField(max_length=16, default=SEVERITY_INFO, db_index=True)
    ip = models.CharField(max_length=64, blank=True, default="")
    user_agent = models.CharField(max_length=512, blank=True, default="")
    detail = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "users_security_audit_events"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
        ]

