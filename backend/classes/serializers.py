import json

from django.core.exceptions import ObjectDoesNotExist, ValidationError as DjangoValidationError
from drf_spectacular.utils import extend_schema_field, extend_schema_serializer
from rest_framework import serializers
from urllib.parse import urlparse
from django.core.validators import URLValidator

from exams.models import MockExam, PracticeTest, PracticeTestPack

from .submission_validation import validate_submission_grade

from .models import (
    Classroom,
    ClassroomMaterial,
    ClassroomMembership,
    ClassPost,
    Assignment,
    Submission,
    SubmissionFile,
    SubmissionAuditEvent,
    ClassComment,
    assignment_target_practice_test_ids,
    filter_practice_targets_by_scope,
    grant_practice_test_library_access_for_assignment,
    raw_target_practice_test_ids_from_fks,
    submission_workflow_status,
)


@extend_schema_serializer(component_name="ClassroomTeacherDetails")
class ClassroomTeacherDetailsSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    email = serializers.EmailField()
    username = serializers.CharField(allow_null=True, required=False)
    first_name = serializers.CharField(allow_blank=True, required=False)
    last_name = serializers.CharField(allow_blank=True, required=False)


@extend_schema_serializer(component_name="AssignmentAssessmentHomeworkSet")
class AssignmentAssessmentHomeworkSetSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    subject = serializers.CharField()
    category = serializers.CharField(allow_blank=True)
    title = serializers.CharField()
    description = serializers.CharField(allow_blank=True)


@extend_schema_serializer(component_name="AssignmentAssessmentHomework")
class AssignmentAssessmentHomeworkSerializer(serializers.Serializer):
    homework_id = serializers.IntegerField()
    set = AssignmentAssessmentHomeworkSetSerializer(allow_null=True, required=False)


@extend_schema_serializer(component_name="AssignmentPracticeBundleTest")
class AssignmentPracticeBundleTestSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    title = serializers.CharField()
    subject = serializers.CharField()


@extend_schema_serializer(component_name="AssignmentCreatedBy")
class AssignmentCreatedBySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    email = serializers.EmailField()
    username = serializers.CharField(allow_null=True, required=False)
    first_name = serializers.CharField(allow_blank=True, required=False)
    last_name = serializers.CharField(allow_blank=True, required=False)


class ClassroomSerializer(serializers.ModelSerializer):
    members_count = serializers.IntegerField(read_only=True)
    my_role = serializers.SerializerMethodField(read_only=True)
    teacher_details = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Classroom
        fields = [
            "id",
            "name",
            "subject",
            "lesson_days",
            "lesson_time",
            "lesson_hours",
            "start_date",
            "room_number",
            "telegram_chat_id",
            "max_students",
            "teacher",
            "teacher_details",
            "join_code",
            "is_active",
            "schedule_summary",
            "created_at",
            "members_count",
            "my_role",
        ]
        read_only_fields = ["join_code", "created_at", "members_count"]

    def get_my_role(self, obj):
        request = self.context.get("request")
        user = getattr(request, "user", None) if request else None
        if not user or not getattr(user, "is_authenticated", False):
            return None
        mem = obj.memberships.filter(user=user).only("role").first()
        return mem.role if mem else None

    @extend_schema_field(ClassroomTeacherDetailsSerializer(allow_null=True, required=False, read_only=True))
    def get_teacher_details(self, obj):
        t = obj.teacher
        if not t:
            return None
        return {
            "id": t.id,
            "email": t.email,
            "username": getattr(t, "username", None),
            "first_name": t.first_name,
            "last_name": t.last_name,
        }


class ClassroomCreateSerializer(serializers.ModelSerializer):
    def validate_name(self, value):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("Name is required.")
        if len(value) > 120:
            raise serializers.ValidationError("Name must be at most 120 characters.")
        return value

    def validate_max_students(self, value):
        if value is not None and value < 1:
            raise serializers.ValidationError("max_students must be at least 1.")
        return value

    def validate_lesson_hours(self, value):
        if value is not None and value < 1:
            raise serializers.ValidationError("lesson_hours must be at least 1.")
        return value

    def validate_teacher(self, value):
        from access import constants as acc_const
        from access.services import actor_subject_probe_for_domain_perm, authorize

        if value is None:
            return value
        if getattr(value, "is_frozen", False):
            raise serializers.ValidationError("Teacher cannot be a frozen account.")
        subj = actor_subject_probe_for_domain_perm(value)
        if subj and authorize(
            value,
            acc_const.PERM_MANAGE_USERS,
            subject=subj,
        ):
            return value
        # Allow keeping the current teacher on update so demoted users do not block all edits.
        instance = getattr(self, "instance", None)
        if instance is not None and instance.teacher_id == value.pk:
            return value
        raise serializers.ValidationError("Teacher must have user-management permission.")

    class Meta:
        model = Classroom
        fields = [
            "id",
            "name",
            "subject",
            "lesson_days",
            "lesson_time",
            "lesson_hours",
            "start_date",
            "room_number",
            "telegram_chat_id",
            "max_students",
            "teacher",
            "is_active",
            "schedule_summary",
            "join_code",
            "created_at",
        ]
        read_only_fields = ["id", "join_code", "created_at"]


class ClassroomMembershipSerializer(serializers.ModelSerializer):
    user = serializers.SerializerMethodField()

    class Meta:
        model = ClassroomMembership
        fields = ["id", "role", "status", "joined_at", "user"]

    def get_user(self, obj):
        u = obj.user
        return {
            "id": u.id,
            "email": u.email,
            "username": getattr(u, "username", None),
            "first_name": u.first_name,
            "last_name": u.last_name,
            "profile_image_url": getattr(u, "profile_image", None).url if getattr(u, "profile_image", None) else None,
        }


class ClassPostSerializer(serializers.ModelSerializer):
    author = serializers.SerializerMethodField()
    content = serializers.CharField(max_length=50_000, trim_whitespace=False)

    class Meta:
        model = ClassPost
        fields = ["id", "content", "created_at", "author"]
        read_only_fields = ["id", "created_at", "author"]

    def validate_content(self, value):
        text = (value or "").strip()
        if not text:
            raise serializers.ValidationError("Announcement content cannot be empty.")
        return value

    def get_author(self, obj):
        u = obj.author
        return {
            "id": u.id,
            "email": u.email,
            "username": getattr(u, "username", None),
            "first_name": u.first_name,
            "last_name": u.last_name,
        }


class AssignmentSerializer(serializers.ModelSerializer):
    title = serializers.CharField(max_length=200)

    created_by = serializers.SerializerMethodField()
    submissions_count = serializers.IntegerField(read_only=True)
    attachment_file_url = serializers.SerializerMethodField(read_only=True)
    attachment_urls = serializers.SerializerMethodField(read_only=True)
    external_url = serializers.CharField(required=False, allow_blank=True)
    mock_exam = serializers.PrimaryKeyRelatedField(
        queryset=MockExam.objects.all(), required=False, allow_null=True
    )
    practice_test = serializers.PrimaryKeyRelatedField(
        queryset=PracticeTest.objects.all(), required=False, allow_null=True
    )
    practice_test_pack = serializers.PrimaryKeyRelatedField(
        queryset=PracticeTestPack.objects.all(), required=False, allow_null=True
    )
    practice_test_ids = serializers.JSONField(required=False, allow_null=True)
    practice_scope = serializers.ChoiceField(
        choices=Assignment.PRACTICE_SCOPE_CHOICES,
        required=False,
        default=Assignment.PRACTICE_SCOPE_BOTH,
    )
    practice_bundle_tests = serializers.SerializerMethodField(read_only=True)
    locks_file_upload = serializers.SerializerMethodField(read_only=True)
    assessment_homework = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Assignment
        fields = [
            "id",
            "title",
            "instructions",
            "due_at",
            "mock_exam",
            "practice_test",
            "practice_test_pack",
            "practice_test_ids",
            "practice_scope",
            "practice_bundle_tests",
            "locks_file_upload",
            "assessment_homework",
            "module",
            "external_url",
            "attachment_file",
            "attachment_file_url",
            "attachment_urls",
            "category",
            "max_score",
            "status",
            "published_at",
            "archived_at",
            "created_at",
            "created_by",
            "submissions_count",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "created_by",
            "submissions_count",
            "practice_bundle_tests",
            "locks_file_upload",
            "attachment_urls",
            "published_at",
            "archived_at",
        ]

    @extend_schema_field(serializers.BooleanField(read_only=True))
    def get_locks_file_upload(self, obj):
        """True when this homework includes assigned practice/mock sections (auto turn-in when tests finish)."""
        # Multi-content bundles are instructional — keep file upload available so a bundle
        # that includes a file deliverable can still be turned in.
        if getattr(obj, "is_multi_content", False):
            return False
        # Also lock for assessment homework (no file submissions / manual grading).
        return bool(assignment_target_practice_test_ids(obj) or getattr(obj, "assessment_homework", None))

    @extend_schema_field(AssignmentAssessmentHomeworkSerializer(allow_null=True, required=False, read_only=True))
    def get_assessment_homework(self, obj):
        """
        When this `classes.Assignment` is backed by an assessment homework, expose enough metadata
        for the homework page to render a start/resume/result CTA.
        """
        hw = getattr(obj, "assessment_homework", None)
        if not hw:
            return None
        aset = getattr(hw, "assessment_set", None)
        if not aset:
            return {"homework_id": hw.id, "set": None}
        return {
            "homework_id": hw.id,
            "set": {
                "id": aset.id,
                "subject": aset.subject,
                "category": aset.category,
                "title": aset.title,
                "description": aset.description,
            },
        }

    @extend_schema_field(AssignmentCreatedBySerializer(read_only=True))
    def get_created_by(self, obj):
        u = obj.created_by
        return {
            "id": u.id,
            "email": u.email,
            "username": getattr(u, "username", None),
            "first_name": u.first_name,
            "last_name": u.last_name,
        }

    @extend_schema_field(serializers.URLField(allow_null=True, read_only=True))
    def get_attachment_file_url(self, obj):
        if not obj.attachment_file:
            return None
        request = self.context.get("request")
        url = obj.attachment_file.url
        if request:
            return request.build_absolute_uri(url)
        return url

    @extend_schema_field(serializers.ListField(child=serializers.URLField(), read_only=True))
    def get_attachment_urls(self, obj):
        """Primary file first, then extra attachments (same order as upload)."""
        request = self.context.get("request")
        urls = []
        if obj.attachment_file:
            u = obj.attachment_file.url
            urls.append(request.build_absolute_uri(u) if request else u)
        for ex in obj.extra_attachments.all():
            u = ex.file.url
            urls.append(request.build_absolute_uri(u) if request else u)
        return urls

    @extend_schema_field(
        serializers.ListField(child=AssignmentPracticeBundleTestSerializer(), read_only=True),
    )
    def get_practice_bundle_tests(self, obj):
        ids = assignment_target_practice_test_ids(obj)
        if not ids:
            return []
        order = {"READING_WRITING": 0, "MATH": 1}
        pts = list(PracticeTest.objects.filter(id__in=ids))
        pts.sort(key=lambda p: (order.get(p.subject, 9), p.id))
        return [
            {"id": p.id, "title": (p.title or "").strip(), "subject": p.subject}
            for p in pts
        ]

    def validate_title(self, value):
        text = (value or "").strip()
        if not text:
            raise serializers.ValidationError("Title is required.")
        return text

    def validate_practice_test_ids(self, value):
        if value is None:
            return None
        if isinstance(value, str):
            s = value.strip()
            if not s or s == "null":
                return None
            value = json.loads(s)
        if not isinstance(value, list):
            raise serializers.ValidationError("practice_test_ids must be a list of integers.")
        if len(value) == 0:
            return None
        out = [int(x) for x in value]
        if len(out) != len(set(out)):
            raise serializers.ValidationError("Duplicate practice test ids.")
        return out

    def validate(self, attrs):
        inst = self.instance

        if inst is not None:
            for fk in ("mock_exam", "practice_test"):
                if fk in attrs and attrs[fk] == "":
                    attrs[fk] = None
            if "practice_test_ids" in attrs:
                v = attrs["practice_test_ids"]
                if v in (None, "", []):
                    attrs["practice_test_ids"] = None
        else:
            # CREATE: multi-content is allowed — a single assignment may bundle a file,
            # a past paper section, an assessment and a practice test at once. Normalize
            # each field independently ("" -> None) and only collapse WITHIN the practice
            # slot (legacy ids vs single describe the same rows). Do NOT null one content
            # type because another is present.
            if attrs.get("practice_test") == "":
                attrs["practice_test"] = None
            pids = attrs.get("practice_test_ids")
            if pids in (None, "", []):
                attrs["practice_test_ids"] = None
            elif len(pids) == 1 and not attrs.get("practice_test"):
                # Mirror a single-id legacy bundle to the canonical practice_test FK.
                attrs["practice_test"] = PracticeTest.objects.filter(
                    pk=pids[0], mock_exam__isnull=True
                ).first()

        attrs = super().validate(attrs)

        mock_id = None
        if "mock_exam" in attrs:
            m = attrs["mock_exam"]
            mock_id = m.pk if m else None
        elif inst is not None:
            mock_id = inst.mock_exam_id

        pt_id = None
        if "practice_test" in attrs:
            t = attrs["practice_test"]
            pt_id = t.pk if t else None
        elif inst is not None:
            pt_id = inst.practice_test_id

        pids = attrs["practice_test_ids"] if "practice_test_ids" in attrs else (
            inst.practice_test_ids if inst is not None else None
        )

        scope = attrs.get("practice_scope")
        if scope is None:
            scope = inst.practice_scope if inst is not None else Assignment.PRACTICE_SCOPE_BOTH
        if not scope:
            scope = Assignment.PRACTICE_SCOPE_BOTH
        attrs["practice_scope"] = scope

        raw = raw_target_practice_test_ids_from_fks(mock_id, pids, pt_id)
        filtered = filter_practice_targets_by_scope(raw, scope)
        if scope != Assignment.PRACTICE_SCOPE_BOTH and raw and not filtered:
            raise serializers.ValidationError(
                {
                    "practice_scope": "No section matches this choice for the selected mock or section (e.g. Math-only choice on an English-only test)."
                }
            )

        return attrs

    def create(self, validated_data):
        inst = super().create(validated_data)
        grant_practice_test_library_access_for_assignment(inst)
        return inst

    def update(self, instance, validated_data):
        inst = super().update(instance, validated_data)
        grant_practice_test_library_access_for_assignment(inst)
        return inst

    def validate_external_url(self, value):
        """
        Accept plain domains like `example.com/file.pdf` by normalizing to https.
        """
        value = (value or "").strip()
        if not value:
            return ""
        parsed = urlparse(value)
        normalized = value if parsed.scheme else f"https://{value}"
        # Reuse DRF URL validator via URLField
        URLValidator()(normalized)
        return normalized


class SubmissionFileSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = SubmissionFile
        fields = ["id", "url", "file_name", "file_type", "created_at"]
        read_only_fields = fields

    def get_url(self, obj):
        request = self.context.get("request")
        url = obj.file.url
        if request:
            return request.build_absolute_uri(url)
        return url


class SubmissionSerializer(serializers.ModelSerializer):
    student = serializers.SerializerMethodField()
    files = SubmissionFileSerializer(many=True, read_only=True)
    attempt = serializers.SerializerMethodField()
    review = serializers.SerializerMethodField()
    workflow_status = serializers.SerializerMethodField()

    class Meta:
        model = Submission
        fields = [
            "id",
            "status",
            "revision",
            "return_note",
            "returned_at",
            "files",
            "attempt",
            "submitted_at",
            "updated_at",
            "student",
            "review",
            "workflow_status",
        ]
        read_only_fields = [
            "id",
            "revision",
            "submitted_at",
            "updated_at",
            "student",
            "review",
            "workflow_status",
            "return_note",
            "returned_at",
        ]

    def get_workflow_status(self, obj):
        return submission_workflow_status(obj)

    def get_student(self, obj):
        u = obj.student
        return {
            "id": u.id,
            "email": u.email,
            "username": getattr(u, "username", None),
            "first_name": u.first_name,
            "last_name": u.last_name,
        }

    def get_review(self, obj):
        try:
            r = obj.review
        except ObjectDoesNotExist:
            return None
        t = r.teacher
        # When status is RETURNED, the linked review (if any) is from the prior cycle — not the active grade.
        if obj.status == Submission.STATUS_RETURNED:
            review_context = "previous_cycle"
        elif obj.status == Submission.STATUS_REVIEWED:
            review_context = "current"
        else:
            review_context = "historical"
        return {
            "grade": str(r.grade) if r.grade is not None else None,
            "max_score": str(r.max_score) if r.max_score is not None else None,
            "feedback": r.feedback,
            "is_auto": r.is_auto,
            "reviewed_at": r.reviewed_at,
            "review_context": review_context,
            "teacher": {
                "id": t.id,
                "email": t.email,
                "first_name": t.first_name,
                "last_name": t.last_name,
            },
        }

    def get_attempt(self, obj):
        a = obj.attempt
        if not a:
            return None
        pt = a.practice_test
        name = (getattr(pt, "title", None) or "").strip() or None
        return {
            "id": a.id,
            "practice_test": pt.id,
            "practice_test_name": name or f"Test #{pt.id}",
            "is_completed": a.is_completed,
            "score": a.score,
            "submitted_at": a.submitted_at,
        }


class SubmitSerializer(serializers.Serializer):
    # Accept "" from multipart forms to clear the linked attempt; integers still allowed.
    attempt_id = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    remove_file_ids = serializers.CharField(required=False, allow_blank=True)
    # Optimistic locking: last known ``Submission.revision`` from GET my-submission.
    expected_revision = serializers.IntegerField(required=False, allow_null=True)
    # JSON array of per-file tokens (same order as ``files``) for idempotent retries.
    file_tokens = serializers.CharField(required=False, allow_blank=True)

    def validate_attempt_id(self, value):
        if value in (None, ""):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            raise serializers.ValidationError("Invalid attempt id.")

    submit = serializers.BooleanField(required=False, default=True)

    def validate(self, attrs):
        import json
        import uuid

        raw = attrs.get("file_tokens")
        tokens: list[str] = []
        if raw:
            try:
                if isinstance(raw, str):
                    arr = json.loads(raw) if raw.strip().startswith("[") else []
                else:
                    arr = raw
                if isinstance(arr, list):
                    tokens = [str(x)[:64] for x in arr]
            except (json.JSONDecodeError, TypeError, ValueError):
                tokens = []
        attrs["file_tokens_list"] = tokens

        n = self.context.get("new_files_count")
        if n is not None and int(n) > 0:
            need = int(n)
            # Backward compatibility: allow file uploads without client-supplied file_tokens.
            # Auto-generate per-file tokens so older clients can still upload successfully.
            if len(tokens) < need:
                for _ in range(need - len(tokens)):
                    tokens.append(uuid.uuid4().hex[:64])
                attrs["file_tokens_list"] = tokens
            need_tokens: list[str] = []
            for i, t in enumerate(tokens[:need]):
                ts = str(t).strip()
                if len(ts) < 8:
                    raise serializers.ValidationError(
                        {"file_tokens": f"Token at index {i} must be at least 8 characters."}
                    )
                need_tokens.append(ts[:64])

            if len(set(need_tokens)) < len(need_tokens):
                raise serializers.ValidationError(
                    {"file_tokens": "Duplicate upload_token values in the same request are not allowed."}
                )

            sub_id = self.context.get("submission_id")
            remove_pks = self.context.get("remove_file_ids") or []
            if sub_id is not None:
                from .models import SubmissionFile

                existing_qs = SubmissionFile.objects.filter(submission_id=sub_id).exclude(upload_token="")
                if remove_pks:
                    existing_qs = existing_qs.exclude(pk__in=remove_pks)
                used = set(existing_qs.values_list("upload_token", flat=True))
                for i, tok in enumerate(need_tokens):
                    if tok in used:
                        raise serializers.ValidationError(
                            {
                                "file_tokens": (
                                    f"Token at index {i} is already used by another file on this submission. "
                                    "Use a new token per upload, or remove the existing file first."
                                )
                            }
                        )
        return attrs


class SubmissionReturnSerializer(serializers.Serializer):
    note = serializers.CharField(required=False, allow_blank=True, max_length=10_000)
    expected_revision = serializers.IntegerField(required=False, allow_null=True)


class SubmissionAuditEventReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubmissionAuditEvent
        fields = ["id", "event_type", "payload", "created_at", "actor_id"]
        read_only_fields = fields


class SubmissionReviewUpsertSerializer(serializers.Serializer):
    grade = serializers.DecimalField(required=False, max_digits=6, decimal_places=2, allow_null=True)
    feedback = serializers.CharField(required=False, allow_blank=True)
    score = serializers.DecimalField(required=False, max_digits=6, decimal_places=2, allow_null=True)
    expected_revision = serializers.IntegerField(required=False, allow_null=True)

    def validate(self, attrs):
        if "score" in attrs and "grade" not in attrs:
            attrs["grade"] = attrs.get("score")
        g = attrs.get("grade")
        if g is not None:
            try:
                validate_submission_grade(g)
            except DjangoValidationError as e:
                raise serializers.ValidationError({"grade": e.messages[0] if e.messages else str(e)})
        return attrs


class ClassCommentSerializer(serializers.ModelSerializer):
    author = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = ClassComment
        fields = ["id", "classroom", "target_type", "target_id", "parent", "content", "author", "created_at", "updated_at"]
        read_only_fields = ["id", "classroom", "author", "created_at", "updated_at"]

    def get_author(self, obj):
        u = obj.author
        return {
            "id": u.id,
            "email": u.email,
            "username": getattr(u, "username", None),
            "first_name": u.first_name,
            "last_name": u.last_name,
        }

    def validate_content(self, value):
        text = (value or "").strip()
        if not text:
            raise serializers.ValidationError("Comment cannot be empty.")
        if len(text) > 10_000:
            raise serializers.ValidationError("Comment is too long.")
        return text

    def validate(self, attrs):
        classroom = attrs.get("classroom") or self.context.get("classroom") or (
            self.instance.classroom if self.instance else None
        )
        t_type = attrs.get("target_type") or (self.instance.target_type if self.instance else None)
        t_id = attrs.get("target_id") if "target_id" in attrs else (self.instance.target_id if self.instance else None)
        parent = attrs.get("parent") if "parent" in attrs else None
        if parent is None and self.instance:
            parent = self.instance.parent
        if classroom and t_type and t_id is not None:
            if t_type == ClassComment.TARGET_POST:
                if not ClassPost.objects.filter(pk=t_id, classroom=classroom).exists():
                    raise serializers.ValidationError({"target_id": "Announcement not found in this class."})
            elif t_type == ClassComment.TARGET_ASSIGNMENT:
                if not Assignment.objects.filter(pk=t_id, classroom=classroom).exists():
                    raise serializers.ValidationError({"target_id": "Assignment not found in this class."})
        if parent and classroom:
            if parent.classroom_id != classroom.pk or parent.target_type != t_type or parent.target_id != t_id:
                raise serializers.ValidationError({"parent": "Reply must belong to the same thread."})
        return attrs


class ClassroomMaterialSerializer(serializers.ModelSerializer):
    """Read serializer for downloadable classroom materials."""

    file_url = serializers.SerializerMethodField()
    teacher_name = serializers.SerializerMethodField()

    class Meta:
        model = ClassroomMaterial
        fields = ["id", "title", "description", "file_url", "teacher_name", "created_at"]
        read_only_fields = fields

    def get_file_url(self, obj) -> str | None:
        if not obj.file:
            return None
        request = self.context.get("request")
        return request.build_absolute_uri(obj.file.url) if request else obj.file.url

    def get_teacher_name(self, obj) -> str | None:
        u = obj.teacher
        if not u:
            return None
        full = f"{(u.first_name or '').strip()} {(u.last_name or '').strip()}".strip()
        return full or getattr(u, "email", None)

