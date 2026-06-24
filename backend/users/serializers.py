from drf_spectacular.utils import extend_schema_field, extend_schema_serializer
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.conf import settings
from django.utils import timezone

from access import constants as acc_const
from access.services import (
    actor_subject_probe_for_domain_perm,
    authorize,
    get_effective_permission_codenames,
    normalized_role,
    user_can_assign_as_class_teacher,
    user_domain_subject,
)
from users.utils_staff import sync_django_staff_flag
from users.phone_utils import normalize_phone

from classes.models import ClassroomMembership

from .models import ExamDateOption, SecurityAuditEvent, User


def _sync_global_user_access(user: User) -> None:
    """Ensure **teachers** have a global DB access row for their domain subject."""
    from access.models import UserAccess

    r = normalized_role(user)
    if r != acc_const.ROLE_TEACHER:
        return
    sj = getattr(user, "subject", None)
    if sj not in acc_const.ALL_DOMAIN_SUBJECTS:
        return
    UserAccess.objects.get_or_create(
        user_id=user.pk,
        subject=sj,
        classroom_id=None,
        defaults={"granted_by_id": user.pk},
    )


class ExamDateOptionSerializer(serializers.ModelSerializer):
    """Full fields for admin CRUD."""

    class Meta:
        model = ExamDateOption
        fields = ["id", "exam_date", "label", "is_active", "sort_order", "created_at"]
        read_only_fields = ["created_at"]


class ExamDateOptionPublicSerializer(serializers.ModelSerializer):
    """Active options shown to students (dropdown)."""

    class Meta:
        model = ExamDateOption
        fields = ["id", "exam_date", "label"]


@extend_schema_serializer(component_name="UserMeLastMockResult")
class UserMeLastMockResultSerializer(serializers.Serializer):
    """Shape of ``UserMeSerializer.get_last_mock_result`` (latest completed practice/mock attempt)."""

    score = serializers.IntegerField(allow_null=True)
    mock_exam_title = serializers.CharField(allow_null=True, allow_blank=True, required=False)
    practice_test_subject = serializers.CharField(allow_null=True, allow_blank=True, required=False)
    completed_at = serializers.CharField(allow_null=True, required=False)


class UserMeSerializer(serializers.ModelSerializer):
    last_mock_result = serializers.SerializerMethodField(read_only=True)
    profile_image_url = serializers.SerializerMethodField(read_only=True)
    clear_profile_image = serializers.BooleanField(write_only=True, required=False)
    role = serializers.SerializerMethodField()
    permissions = serializers.SerializerMethodField()
    is_admin = serializers.SerializerMethodField(read_only=True)
    telegram_linked = serializers.SerializerMethodField()
    security_step_up_active = serializers.SerializerMethodField()
    has_recent_security_alerts = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "username",
            "first_name",
            "last_name",
            "phone_number",
            "is_frozen",
            "is_admin",
            "telegram_linked",
            "profile_image",
            "profile_image_url",
            "sat_exam_date",
            "target_score",
            "target_english",
            "target_math",
            "last_mock_result",
            "clear_profile_image",
            "role",
            "subject",
            "permissions",
            "last_password_change",
            "security_step_up_active",
            "has_recent_security_alerts",
        ]
        extra_kwargs = {
            "profile_image": {"required": False, "allow_null": True},
            "username": {"required": False},
            "first_name": {"required": False},
            "last_name": {"required": False},
            "email": {"required": False},
            "is_frozen": {"read_only": True},
            "subject": {"read_only": True},
            "last_password_change": {"read_only": True},
        }

    def validate_username(self, value):
        if value is not None and value != "" and len(value.strip()) < 3:
            raise serializers.ValidationError("Username must be at least 3 characters.")
        return value

    def validate_first_name(self, value):
        if value is not None and value.strip() and len(value.strip()) < 3:
            raise serializers.ValidationError("First name must be at least 3 characters.")
        return value

    def validate_last_name(self, value):
        if value is not None and value.strip() and len(value.strip()) < 3:
            raise serializers.ValidationError("Last name must be at least 3 characters.")
        return value

    def validate_email(self, value):
        user_qs = User.objects.filter(email__iexact=value)
        if self.instance and self.instance.pk:
            user_qs = user_qs.exclude(pk=self.instance.pk)
        if user_qs.exists():
            raise serializers.ValidationError("user with this email already exists.")
        return value

    def validate_target_score(self, value):
        if value is None:
            return value
        if value < 400 or value > 1600:
            raise serializers.ValidationError("Target score must be between 400 and 1600.")
        return value

    def _validate_section_target(self, value):
        if value is None:
            return value
        if value < 200 or value > 800:
            raise serializers.ValidationError("Section target must be between 200 and 800.")
        return value

    def validate_target_english(self, value):
        return self._validate_section_target(value)

    def validate_target_math(self, value):
        return self._validate_section_target(value)

    def validate_profile_image(self, value):
        if value is None:
            return value
        max_b = int(getattr(settings, "USER_PROFILE_MAX_IMAGE_BYTES", 5 * 1024 * 1024))
        size = int(getattr(value, "size", 0) or 0)
        if size > max_b:
            raise serializers.ValidationError(f"Profile image too large. Maximum is {max_b} bytes.")
        ct = str(getattr(value, "content_type", "") or "").lower()
        if ct and not ct.startswith("image/"):
            raise serializers.ValidationError("Invalid profile image content type.")
        return value

    def validate_sat_exam_date(self, value):
        """Students may only set a date that exists in the admin-managed active list."""
        if value is None:
            return value
        if not ExamDateOption.objects.filter(exam_date=value, is_active=True).exists():
            raise serializers.ValidationError(
                "This exam date is not available. Please choose one from the list."
            )
        return value

    def validate_phone_number(self, value):
        if value is None or (isinstance(value, str) and not str(value).strip()):
            return None
        try:
            normalized = normalize_phone(value)
        except ValueError as e:
            raise serializers.ValidationError(str(e)) from e
        if not normalized:
            return None
        qs = User.objects.filter(phone_number=normalized)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("This phone number is already in use.")
        return normalized

    @extend_schema_field(serializers.URLField(allow_null=True, read_only=True))
    def get_profile_image_url(self, obj):
        if not obj.profile_image:
            return None
        request = self.context.get("request")
        url = obj.profile_image.url
        if request:
            return request.build_absolute_uri(url)
        return url

    @extend_schema_field(UserMeLastMockResultSerializer(allow_null=True, required=False, read_only=True))
    def get_last_mock_result(self, obj):
        from exams.models import TestAttempt

        att = (
            TestAttempt.objects.filter(student=obj, is_completed=True)
            .select_related("practice_test__mock_exam")
            .order_by("-submitted_at", "-id")
            .first()
        )
        if not att:
            return None
        mock = att.practice_test.mock_exam if att.practice_test else None
        completed = att.submitted_at
        return {
            "score": att.score,
            "mock_exam_title": mock.title if mock else None,
            "practice_test_subject": att.practice_test.subject if att.practice_test else None,
            "completed_at": completed.isoformat() if completed else None,
        }

    def update(self, instance, validated_data):
        clear = validated_data.pop("clear_profile_image", False)
        if clear:
            if instance.profile_image:
                instance.profile_image.delete(save=False)
            instance.profile_image = None
        return super().update(instance, validated_data)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data.pop("profile_image", None)
        return data

    @extend_schema_field(serializers.CharField(read_only=True))
    def get_role(self, obj):
        return obj.role

    @extend_schema_field(serializers.BooleanField(read_only=True))
    def get_is_admin(self, obj):
        return bool(obj.is_admin)

    @extend_schema_field(serializers.BooleanField(read_only=True))
    def get_telegram_linked(self, obj):
        return obj.telegram_id is not None

    @extend_schema_field(serializers.BooleanField(read_only=True))
    def get_security_step_up_active(self, obj):
        until = getattr(obj, "security_step_up_required_until", None)
        if not until:
            return False
        return bool(until > timezone.now())

    @extend_schema_field(serializers.BooleanField(read_only=True))
    def get_has_recent_security_alerts(self, obj):
        from users.models import SecurityAuditEvent
        from datetime import timedelta

        since = timezone.now() - timedelta(days=7)
        return SecurityAuditEvent.objects.filter(
            user=obj, severity__in=("warning", "critical"), created_at__gte=since
        ).exists()

    @extend_schema_field(serializers.ListField(child=serializers.CharField(), read_only=True))
    def get_permissions(self, obj):
        return sorted(get_effective_permission_codenames(obj))


class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        perms = sorted(get_effective_permission_codenames(user))
        token["is_admin"] = user.is_admin
        token["role"] = user.role
        token["subject"] = getattr(user, "subject", None) or ""
        token["is_frozen"] = user.is_frozen
        token["permissions"] = perms
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        u = self.user
        try:
            if getattr(u, "security_step_up_required_until", None):
                u.security_step_up_required_until = None
                u.save(update_fields=["security_step_up_required_until"])
        except Exception:
            # Never fail password login if adaptive-security columns drift or DB is mid-migrate.
            pass
        data["is_admin"] = u.is_admin
        data["role"] = u.role
        data["subject"] = getattr(u, "subject", None) or ""
        data["is_frozen"] = u.is_frozen
        data["permissions"] = sorted(get_effective_permission_codenames(u))
        return data


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False)
    is_admin = serializers.BooleanField(write_only=True, required=False)
    role = serializers.CharField(required=False)
    subject = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    class_teacher_eligible = serializers.SerializerMethodField()
    bulk_assign_profile = serializers.SerializerMethodField()

    def validate_username(self, value):
        if value == '':
            return None
        if value is not None and len(value.strip()) < 3:
            raise serializers.ValidationError("Username must be at least 3 characters.")
        return value

    def validate_first_name(self, value):
        if value is not None and value.strip() and len(value.strip()) < 3:
            raise serializers.ValidationError("First name must be at least 3 characters.")
        return value

    def validate_last_name(self, value):
        if value is not None and value.strip() and len(value.strip()) < 3:
            raise serializers.ValidationError("Last name must be at least 3 characters.")
        return value

    def validate_email(self, value):
        # Manual unique check to avoid issues with instance exclusion in some environments
        user_qs = User.objects.filter(email__iexact=value)
        if self.instance and self.instance.pk:
            user_qs = user_qs.exclude(pk=self.instance.pk)
        
        if user_qs.exists():
            raise serializers.ValidationError("user with this email already exists.")
        return value

    def validate_phone_number(self, value):
        if value in (None, ""):
            return None
        try:
            normalized = normalize_phone(value)
        except ValueError as e:
            raise serializers.ValidationError(str(e)) from e
        if not normalized:
            return None
        qs = User.objects.filter(phone_number=normalized)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("This phone number is already in use.")
        return normalized

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "username",
            "first_name",
            "last_name",
            "phone_number",
            "role",
            "subject",
            "class_teacher_eligible",
            "bulk_assign_profile",
            "is_admin",
            "is_active",
            "is_frozen",
            "date_joined",
            "password",
        ]
        read_only_fields = ["date_joined"]

    def _normalize_role(self, raw: str | None) -> str | None:
        if raw is None:
            return None
        if not isinstance(raw, str):
            return None
        v = raw.strip().lower()
        if not v:
            return None
        if v in acc_const.CANONICAL_ROLES:
            return v
        return None

    def validate_subject(self, value):
        if value in (None, ""):
            return None
        v = str(value).strip().lower()
        if v not in acc_const.ALL_DOMAIN_SUBJECTS:
            raise serializers.ValidationError('Subject must be "math" or "english".')
        return v

    def get_class_teacher_eligible(self, obj):
        return user_can_assign_as_class_teacher(obj)

    def get_bulk_assign_profile(self, obj):
        """
        Students only: DB subject grants (UserAccess) + classrooms for bulk-assign UI.
        Mirrors ``student_has_any_subject_grant`` / classroom visibility used in admin lists.
        """
        if normalized_role(obj) != acc_const.ROLE_STUDENT:
            return None
        grant_subjects = {g.subject for g in obj.access_grants.all()}
        classrooms = []
        seen: set[int] = set()
        for m in obj.class_memberships.all():
            if getattr(m, "role", None) != ClassroomMembership.ROLE_STUDENT:
                continue
            cid = m.classroom_id
            if cid in seen:
                continue
            seen.add(cid)
            classrooms.append(
                {
                    "id": cid,
                    "name": m.classroom.name,
                    "subject": m.classroom.subject,
                }
            )
        return {
            "subject_grants": {
                "math": acc_const.DOMAIN_MATH in grant_subjects,
                "english": acc_const.DOMAIN_ENGLISH in grant_subjects,
            },
            "classrooms": classrooms,
        }

    def _incoming_role_code(self):
        data = getattr(self, "initial_data", None) or {}
        if not isinstance(data, dict):
            return None
        rc = self._normalize_role(data.get("role_code") or data.get("role"))
        if rc:
            return rc
        if data.get("is_admin") is True:
            return acc_const.ROLE_ADMIN
        if data.get("is_admin") is False:
            return acc_const.ROLE_STUDENT
        return None

    def _resolve_system_role_for_write(self, *, instance=None):
        rc = self._incoming_role_code()
        request = self.context.get("request")
        actor = getattr(request, "user", None) if request else None

        if rc:
            if not actor or not actor.is_authenticated:
                raise serializers.ValidationError(
                    {"role": "Authentication required to set role."}
                )
            actor_subj = actor_subject_probe_for_domain_perm(actor)
            if not actor_subj or not (
                authorize(actor, acc_const.PERM_ASSIGN_ACCESS, subject=actor_subj)
                or authorize(actor, acc_const.PERM_MANAGE_USERS, subject=actor_subj)
            ):
                raise serializers.ValidationError(
                    {"role": "You do not have permission to assign roles."}
                )
            adom = user_domain_subject(actor)
            if adom and normalized_role(actor) == acc_const.ROLE_TEACHER:
                incoming = (self.initial_data or {}).get("subject")
                if incoming not in (None, "") and str(incoming).strip().lower() != adom:
                    raise serializers.ValidationError(
                        {"subject": "You may only assign users within your subject."}
                    )
            return rc

        if instance is None:
            return acc_const.ROLE_STUDENT
        return None

    def create(self, validated_data):
        request = self.context.get("request")
        actor = getattr(request, "user", None) if request else None
        validated_data.pop("scope", None)

        validated_data.pop("is_admin", None)
        validated_data.pop("system_role", None)
        role = self._resolve_system_role_for_write(instance=None)
        validated_data["role"] = role

        subj = validated_data.get("subject")
        if role == acc_const.ROLE_TEACHER:
            if subj not in acc_const.ALL_DOMAIN_SUBJECTS:
                raise serializers.ValidationError(
                    {"subject": "Teacher accounts require subject: math or english."}
                )
        elif role in (acc_const.ROLE_ADMIN, acc_const.ROLE_TEST_ADMIN, acc_const.ROLE_SUPER_ADMIN):
            validated_data["subject"] = None
        elif role == acc_const.ROLE_STUDENT:
            validated_data["subject"] = None

        password = validated_data.pop("password", None)
        user = super().create(validated_data)
        if password:
            user.set_password(password)
            user.last_password_change = timezone.now()
            user.security_step_up_required_until = None
            user.save()
        sync_django_staff_flag(user)
        user.refresh_from_db()
        _sync_global_user_access(user)
        return user

    def update(self, instance, validated_data):
        request = self.context.get("request")
        actor = getattr(request, "user", None) if request else None
        validated_data.pop("scope", None)

        validated_data.pop("is_admin", None)
        new_role = self._resolve_system_role_for_write(instance=instance)
        if new_role is not None:
            instance.role = new_role
            instance.save(update_fields=["role"])

        eff_role = self._normalize_role(instance.role) or acc_const.ROLE_STUDENT
        if "subject" in validated_data:
            subj = validated_data.get("subject")
            if eff_role == acc_const.ROLE_TEACHER:
                if subj not in acc_const.ALL_DOMAIN_SUBJECTS:
                    raise serializers.ValidationError(
                        {"subject": "Teacher accounts require subject: math or english."}
                    )
            elif eff_role in (
                acc_const.ROLE_ADMIN,
                acc_const.ROLE_TEST_ADMIN,
                acc_const.ROLE_SUPER_ADMIN,
                acc_const.ROLE_STUDENT,
            ):
                validated_data["subject"] = None

        password = validated_data.pop("password", None)
        user = super().update(instance, validated_data)
        if password:
            user.set_password(password)
            user.last_password_change = timezone.now()
            user.security_step_up_required_until = None
            user.save()
        sync_django_staff_flag(user)
        user.refresh_from_db()
        eff = self._normalize_role(user.role) or acc_const.ROLE_STUDENT
        sj = getattr(user, "subject", None)
        if eff == acc_const.ROLE_TEACHER:
            if sj not in acc_const.ALL_DOMAIN_SUBJECTS:
                raise serializers.ValidationError(
                    {"subject": "Teacher accounts require subject: math or english."}
                )
        elif eff in (acc_const.ROLE_ADMIN, acc_const.ROLE_TEST_ADMIN) and sj not in (None, ""):
            raise serializers.ValidationError(
                {"subject": "Admin and test_admin accounts must not have a subject set."}
            )
        _sync_global_user_access(user)
        return user


class SecurityAuditEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = SecurityAuditEvent
        fields = ("id", "event_type", "severity", "ip", "user_agent", "detail", "created_at")

