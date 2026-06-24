import re
import unicodedata

from django.contrib.auth import get_user_model
from django.core.exceptions import NON_FIELD_ERRORS, ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.settings import api_settings
from django.utils import timezone
from drf_spectacular.utils import extend_schema_field, extend_schema_serializer

from .models import (
    BulkAssignmentDispatch,
    MockExam,
    Module,
    PortalMockExam,
    PracticeTest,
    PracticeTestPack,
    Question,
    TestAttempt,
)

User = get_user_model()


def _normalize_platform_subject_value(raw):
    """Canonical READING_WRITING | MATH for API output (legacy rows / typos)."""
    if raw is None:
        return None
    s = str(raw).strip()
    s = re.sub(r"[\u200b-\u200f\ufeff]", "", s).strip()
    if not s:
        return None
    s = unicodedata.normalize("NFKC", s).strip()
    if not s:
        return None
    u = re.sub(r"\s+", "_", s.upper())
    if u in ("MATH", "MATHEMATICS", "MATHS"):
        return "MATH"
    if u in (
        "READING_WRITING",
        "RW",
        "READING",
        "WRITING",
        "ENGLISH",
        "R&W",
        "R_AND_W",
    ) or ("READING" in u and "WRITING" in u):
        return "READING_WRITING"
    low = s.lower()
    if low in ("math", "mathematics", "maths"):
        return "MATH"
    if "reading" in low and "writing" in low:
        return "READING_WRITING"
    return raw


class QuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Question
        fields = ['id', 'question_type', 'question_text', 'question_prompt', 'question_image', 'is_math_input',
                  'option_a_image', 'option_b_image', 'option_c_image', 'option_d_image']
        
    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['options'] = instance.get_options()
        return representation

class ModuleSerializer(serializers.ModelSerializer):
    questions = QuestionSerializer(many=True, read_only=True)
    
    class Meta:
        model = Module
        fields = ['id', 'module_order', 'time_limit_minutes', 'questions']

class ModuleListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Module
        fields = ['id', 'module_order', 'time_limit_minutes']


@extend_schema_serializer(component_name="ExamAttemptModuleDetail")
class ExamAttemptModuleSerializer(ModuleSerializer):
    """Serialized ``current_module_details`` payload (questions + timings) for runners / status."""

    class Meta(ModuleSerializer.Meta):
        pass


class AttemptModuleQuestionResultSerializer(serializers.Serializer):
    """Mirror of ``TestAttempt.get_module_results`` inner question rows (review payload)."""

    id = serializers.IntegerField()
    is_correct = serializers.BooleanField()
    student_answer = serializers.JSONField(allow_null=True)
    correct_answers = serializers.CharField()
    score = serializers.IntegerField()
    text = serializers.CharField()
    question_prompt = serializers.CharField(allow_blank=True, required=False, default="")
    image = serializers.CharField(required=False, allow_null=True)
    type = serializers.CharField()
    options = serializers.JSONField(allow_null=True)
    is_math_input = serializers.BooleanField()


class AttemptModuleResultsItemSerializer(serializers.Serializer):
    module_id = serializers.IntegerField()
    module_order = serializers.IntegerField()
    module_earned = serializers.IntegerField()
    capped_earned = serializers.IntegerField()
    questions = AttemptModuleQuestionResultSerializer(many=True)


class PracticeTestMockExamBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = MockExam
        fields = ["id", "title", "kind", "practice_date"]


class PortalMockExamStudentSerializer(serializers.ModelSerializer):
    """Student mock list: no nested PracticeTest objects."""

    mock_exam_id = serializers.IntegerField(source="mock_exam.id", read_only=True)
    title = serializers.CharField(source="mock_exam.title", read_only=True)
    practice_date = serializers.DateField(source="mock_exam.practice_date", read_only=True)
    kind = serializers.CharField(source="mock_exam.kind", read_only=True)
    is_published = serializers.BooleanField(source="mock_exam.is_published", read_only=True)
    section_test_ids = serializers.SerializerMethodField()

    def get_section_test_ids(self, obj):
        # Use .all() so Django's prefetch cache is hit when mock_exam__tests is prefetched.
        # .values_list() bypasses the cache and always issues a new query.
        return [t.id for t in obj.mock_exam.tests.all()]

    class Meta:
        model = PortalMockExam
        fields = ["id", "mock_exam_id", "title", "practice_date", "kind", "is_published", "section_test_ids"]


class PracticeTestPackStudentSerializer(serializers.ModelSerializer):
    """Student-facing practice test pack: pack metadata + shallow section list."""

    sections = serializers.SerializerMethodField()

    def get_sections(self, obj):
        qs = (
            obj.sections.filter(modules__questions__isnull=False)
            .prefetch_related("modules")
            .distinct()
        )
        return [
            {
                "id": pt.id,
                "title": pt.title,
                "subject": pt.subject,
                "module_count": pt.modules.count(),
            }
            for pt in qs
        ]

    class Meta:
        model = PracticeTestPack
        fields = ["id", "title", "description", "is_published", "sections", "created_at"]


class AttemptPracticeTestDetailsSerializer(serializers.Serializer):
    """
    Embedded snapshot on ``TestAttempt`` via ``practice_test_details`` (SerializerMethodField).
    Schema must mirror ``get_practice_test_details`` for OpenAPI.
    """

    id = serializers.IntegerField()
    subject = serializers.CharField()
    title = serializers.CharField()
    label = serializers.CharField(allow_blank=True, allow_null=True, required=False)
    form_type = serializers.CharField(allow_blank=True, allow_null=True, required=False)
    practice_date = serializers.CharField(allow_blank=True, allow_null=True, required=False)
    collection_name = serializers.CharField(allow_blank=True, allow_null=True, required=False)
    is_active = serializers.BooleanField(required=False)
    mock_exam_id = serializers.IntegerField(allow_null=True, required=False)
    mock_kind = serializers.CharField(allow_blank=True, allow_null=True, required=False)
    modules = ModuleListSerializer(many=True)


class PracticeTestSerializer(serializers.ModelSerializer):
    """Student practice library: past papers only (mock_exam_id must be null for /exams/ list)."""

    modules = ModuleListSerializer(many=True, read_only=True)
    subject = serializers.CharField()
    mock_exam_id = serializers.IntegerField(read_only=True, allow_null=True)

    class Meta:
        model = PracticeTest
        fields = [
            "id",
            "title",
            "practice_date",
            "subject",
            "label",
            "form_type",
            "collection_name",
            "is_published",
            "modules",
            "created_at",
            "mock_exam_id",
        ]
        read_only_fields = ["created_at", "mock_exam_id"]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        canon = _normalize_platform_subject_value(data.get("subject"))
        if canon is not None:
            data["subject"] = canon
        return data


class MockExamSerializer(serializers.ModelSerializer):
    tests = PracticeTestSerializer(many=True, read_only=True)

    class Meta:
        model = MockExam
        fields = [
            "id",
            "title",
            "practice_date",
            "is_active",
            "is_published",
            "published_at",
            "kind",
            "midterm_subject",
            "midterm_scoring_scale",
            "midterm_module_count",
            "midterm_module1_minutes",
            "midterm_module2_minutes",
            "tests",
        ]

from users.serializers import UserSerializer
from .attempt_timing import get_active_module_timing

class TestAttemptSerializer(serializers.ModelSerializer):
    practice_test_details = serializers.SerializerMethodField()
    # Critical: some legacy attempts can have current_state=MODULE_*_ACTIVE while current_module is null
    # (partial writes, old code paths, or manual edits). The UI requires a module payload to render.
    # We therefore compute this field and fall back to inferring the module from state.
    current_module_details = serializers.SerializerMethodField()
    student_details = UserSerializer(source='student', read_only=True)
    is_expired = serializers.SerializerMethodField()
    module_results = serializers.SerializerMethodField()
    server_now = serializers.SerializerMethodField()
    current_module_saved_answers = serializers.SerializerMethodField()
    current_module_flagged_questions = serializers.SerializerMethodField()
    remaining_seconds = serializers.SerializerMethodField()
    module_duration_seconds = serializers.SerializerMethodField()
    module_started_at = serializers.SerializerMethodField()
    active_module_order = serializers.SerializerMethodField()
    can_submit = serializers.SerializerMethodField()
    can_resume = serializers.SerializerMethodField()
    results_ready = serializers.SerializerMethodField()
    engine_phase = serializers.SerializerMethodField()
    scoring_notice = serializers.SerializerMethodField()
    is_paused = serializers.SerializerMethodField()

    @extend_schema_field(serializers.BooleanField())
    def get_is_paused(self, obj):
        return getattr(obj, "pause_started_at", None) is not None

    @extend_schema_field(serializers.BooleanField())
    def get_is_expired(self, obj):
        return getattr(obj, 'is_expired', False)

    @extend_schema_field(
        serializers.ListSerializer(
            child=AttemptModuleResultsItemSerializer(),
            allow_null=True,
            required=False,
        )
    )
    def get_module_results(self, obj):
        return obj.get_module_results() if obj.is_completed else None

    @extend_schema_field(serializers.DateTimeField())
    def get_server_now(self, obj):
        return timezone.now().isoformat()

    @extend_schema_field(serializers.DateTimeField(allow_null=True, required=False))
    def get_module_started_at(self, obj):
        mod = getattr(obj, "current_module", None)
        if mod is not None:
            mo = getattr(mod, "module_order", None)
            if mo == 1:
                v = getattr(obj, "module_1_started_at", None) or getattr(obj, "current_module_start_time", None)
                return v.isoformat() if v else None
            if mo == 2:
                v = getattr(obj, "module_2_started_at", None) or getattr(obj, "current_module_start_time", None)
                return v.isoformat() if v else None
        v = getattr(obj, "current_module_start_time", None)
        return v.isoformat() if v else None

    @extend_schema_field(serializers.IntegerField(allow_null=True, required=False))
    def get_module_duration_seconds(self, obj):
        mod = getattr(obj, "current_module", None)
        if not mod:
            # mirror serializer inference so the UI can still render safely
            st = getattr(obj, "current_state", None)
            if st == TestAttempt.STATE_MODULE_1_ACTIVE:
                mod = obj.practice_test.modules.filter(module_order=1).order_by("id").first()
            elif st == TestAttempt.STATE_MODULE_2_ACTIVE:
                mod = obj.practice_test.modules.filter(module_order=2).order_by("id").first()
        if not mod:
            return None
        try:
            mins = int(getattr(mod, "time_limit_minutes", 0) or 0)
        except (TypeError, ValueError):
            mins = 0
        return max(0, mins * 60)

    @extend_schema_field(serializers.IntegerField(allow_null=True, required=False))
    def get_remaining_seconds(self, obj):
        """Server-derived from stored module anchors + ``Module.time_limit_minutes`` (never client clock)."""
        try:
            st = getattr(obj, "current_state", None)
            if st in (TestAttempt.STATE_SCORING, TestAttempt.STATE_COMPLETED):
                return None
            timing = get_active_module_timing(obj)
            return int(timing.remaining_seconds) if timing else None
        except Exception:
            return None

    @extend_schema_field(
        serializers.ChoiceField(
            choices=[
                "pending",
                "active",
                "scoring",
                "completed",
                "abandoned",
                "other",
            ]
        )
    )
    def get_engine_phase(self, obj):
        """Stable UI phase: ``pending`` | ``active`` | ``scoring`` | ``completed``."""
        st = getattr(obj, "current_state", None)
        if getattr(obj, "is_completed", False) or st == TestAttempt.STATE_COMPLETED:
            return "completed"
        if st == TestAttempt.STATE_SCORING:
            return "scoring"
        if st in (TestAttempt.STATE_MODULE_1_ACTIVE, TestAttempt.STATE_MODULE_2_ACTIVE):
            return "active"
        if st == TestAttempt.STATE_NOT_STARTED:
            return "pending"
        if st == TestAttempt.STATE_ABANDONED:
            return "abandoned"
        return "other"

    @extend_schema_field(serializers.CharField(allow_null=True, required=False, allow_blank=False))
    def get_scoring_notice(self, obj):
        if getattr(obj, "current_state", None) == TestAttempt.STATE_SCORING:
            return (
                "Your test responses are queued for scoring on the server. "
                "This screen will update automatically when results are ready."
            )
        return None

    @extend_schema_field(serializers.IntegerField(allow_null=True, required=False))
    def get_active_module_order(self, obj):
        mod = getattr(obj, "current_module", None)
        if mod and getattr(mod, "module_order", None) in (1, 2):
            return int(mod.module_order)
        # fall back to state inference
        st = getattr(obj, "current_state", None)
        if st == TestAttempt.STATE_MODULE_1_ACTIVE:
            return 1
        if st == TestAttempt.STATE_MODULE_2_ACTIVE:
            return 2
        return None

    @extend_schema_field(serializers.BooleanField())
    def get_can_submit(self, obj):
        st = getattr(obj, "current_state", None)
        if st not in (TestAttempt.STATE_MODULE_1_ACTIVE, TestAttempt.STATE_MODULE_2_ACTIVE):
            return False
        try:
            timing = get_active_module_timing(obj)
            if timing and timing.is_expired:
                return False
        except Exception:
            pass
        return True

    @extend_schema_field(serializers.BooleanField())
    def get_can_resume(self, obj):
        st = getattr(obj, "current_state", None)
        if getattr(obj, "is_completed", False) or st == TestAttempt.STATE_COMPLETED:
            return False
        return bool(st in (TestAttempt.STATE_NOT_STARTED, TestAttempt.STATE_MODULE_1_ACTIVE, TestAttempt.STATE_MODULE_2_ACTIVE, TestAttempt.STATE_ABANDONED, TestAttempt.STATE_MODULE_1_SUBMITTED, TestAttempt.STATE_MODULE_2_SUBMITTED))

    @extend_schema_field(serializers.BooleanField())
    def get_results_ready(self, obj):
        return bool(getattr(obj, "is_completed", False) and getattr(obj, "current_state", None) == TestAttempt.STATE_COMPLETED)

    @extend_schema_field(ExamAttemptModuleSerializer(allow_null=True, required=False))
    def get_current_module_details(self, obj):
        mod = getattr(obj, "current_module", None)
        if mod:
            return ModuleSerializer(mod).data

        st = getattr(obj, "current_state", None)
        if st == TestAttempt.STATE_MODULE_1_ACTIVE:
            m = obj.practice_test.modules.filter(module_order=1).order_by("id").first()
            return ModuleSerializer(m).data if m else None
        if st == TestAttempt.STATE_MODULE_2_ACTIVE:
            m = obj.practice_test.modules.filter(module_order=2).order_by("id").first()
            return ModuleSerializer(m).data if m else None
        return None

    @extend_schema_field(
        serializers.DictField(
            child=serializers.JSONField(allow_null=True),
            allow_null=True,
            required=False,
        )
    )
    def get_current_module_saved_answers(self, obj):
        """
        Resume support: return saved answers for the currently active module only.
        Never include correct answers; review endpoint remains gated behind completion.
        """
        mod = getattr(obj, "current_module", None)
        if not mod:
            st = getattr(obj, "current_state", None)
            if st == TestAttempt.STATE_MODULE_1_ACTIVE:
                mod = obj.practice_test.modules.filter(module_order=1).order_by("id").first()
            elif st == TestAttempt.STATE_MODULE_2_ACTIVE:
                mod = obj.practice_test.modules.filter(module_order=2).order_by("id").first()
            if not mod:
                return None
        try:
            return (obj.module_answers or {}).get(str(mod.id), {}) or {}
        except Exception:
            return {}

    @extend_schema_field(
        serializers.ListField(
            child=serializers.IntegerField(),
            allow_null=True,
            required=False,
        )
    )
    def get_current_module_flagged_questions(self, obj):
        mod = getattr(obj, "current_module", None)
        if not mod:
            # If we inferred a module for rendering, mirror that for resume support.
            st = getattr(obj, "current_state", None)
            if st == TestAttempt.STATE_MODULE_1_ACTIVE:
                mod = obj.practice_test.modules.filter(module_order=1).order_by("id").first()
            elif st == TestAttempt.STATE_MODULE_2_ACTIVE:
                mod = obj.practice_test.modules.filter(module_order=2).order_by("id").first()
            if not mod:
                return None
        try:
            return (obj.flagged_questions or {}).get(str(mod.id), []) or []
        except Exception:
            return []

    @extend_schema_field(AttemptPracticeTestDetailsSerializer)
    def get_practice_test_details(self, obj):
        pt = obj.practice_test
        mock = getattr(pt, "mock_exam", None)
        subj = _normalize_platform_subject_value(pt.subject) or pt.subject
        collection_name = (getattr(pt, "collection_name", None) or "").strip()
        pt_title = (getattr(pt, "title", None) or "").strip()
        mock_title = (getattr(mock, "title", None) or "").strip() if mock is not None else ""
        resolved_title = pt_title or mock_title or collection_name

        if mock is not None and getattr(mock, "practice_date", None):
            practice_date_iso = mock.practice_date.isoformat()
        elif getattr(pt, "practice_date", None):
            practice_date_iso = pt.practice_date.isoformat()
        else:
            practice_date_iso = None

        return {
            "id": pt.id,
            "subject": subj,
            "title": resolved_title,
            "label": getattr(pt, "label", "") or "",
            "form_type": getattr(pt, "form_type", "") or "INTERNATIONAL",
            "practice_date": practice_date_iso,
            "collection_name": collection_name,
            "is_active": getattr(mock, "is_active", True) if mock is not None else True,
            "mock_exam_id": getattr(pt, "mock_exam_id", None),
            "mock_kind": getattr(mock, "kind", None) if mock is not None else None,
            "modules": ModuleListSerializer(pt.modules.all(), many=True).data,
        }
    
    class Meta:
        model = TestAttempt
        fields = [
            'id', 'practice_test', 'practice_test_details', 'student', 'student_details', 'started_at', 'submitted_at', 
            'current_module', 'current_module_details', 'current_module_start_time',
            'current_state',
            'module_1_started_at', 'module_1_submitted_at',
            'module_2_started_at', 'module_2_submitted_at',
            'scoring_started_at', 'completed_at',
            'version_number',
            'is_completed', 'is_expired', 'score', 'completed_modules', 'module_results',
            'server_now',
            'current_module_saved_answers',
            'current_module_flagged_questions',
            'remaining_seconds',
            'module_duration_seconds',
            'module_started_at',
            'active_module_order',
            'can_submit',
            'can_resume',
            'results_ready',
            'engine_phase',
            'scoring_notice',
            'is_paused',
        ]

        read_only_fields = [
            'student',
            'started_at',
            'submitted_at',
            'current_module',
            'current_module_start_time',
            'current_state',
            'module_1_started_at', 'module_1_submitted_at',
            'module_2_started_at', 'module_2_submitted_at',
            'scoring_started_at', 'completed_at',
            'version_number',
            'is_completed',
            'score',
            'completed_modules',
            'server_now',
            'remaining_seconds',
            'module_duration_seconds',
            'module_started_at',
            'active_module_order',
            'can_submit',
            'can_resume',
            'results_ready',
            'engine_phase',
            'scoring_notice',
        ]

# ── Admin Serializers ────────────────────────────────────────────────────────

class AdminQuestionSerializer(serializers.ModelSerializer):
    correct_answer = serializers.CharField(source='correct_answers', required=True)
    module_id = serializers.IntegerField(read_only=True)
    practice_test_id = serializers.IntegerField(source="module.practice_test_id", read_only=True)
    question_text = serializers.CharField(required=False, allow_blank=True, default="")
    option_a = serializers.CharField(required=False, allow_blank=True)
    option_b = serializers.CharField(required=False, allow_blank=True)
    option_c = serializers.CharField(required=False, allow_blank=True)
    option_d = serializers.CharField(required=False, allow_blank=True)
    clear_question_image = serializers.BooleanField(write_only=True, required=False)
    clear_option_a_image = serializers.BooleanField(write_only=True, required=False)
    clear_option_b_image = serializers.BooleanField(write_only=True, required=False)
    clear_option_c_image = serializers.BooleanField(write_only=True, required=False)
    clear_option_d_image = serializers.BooleanField(write_only=True, required=False)

    class Meta:
        model = Question
        fields = ['id', 'module_id', 'practice_test_id', 'question_type', 'question_text', 'question_prompt', 'question_image',
                  'is_math_input', 'correct_answer', 'score', 'explanation', 'order',
                  'option_a', 'option_b', 'option_c', 'option_d',
                  'option_a_image', 'option_b_image', 'option_c_image', 'option_d_image',
                  'clear_question_image', 'clear_option_a_image', 'clear_option_b_image',
                  'clear_option_c_image', 'clear_option_d_image']

    def create(self, validated_data):
        # Clear flags are serializer-only controls and must not be passed to model create().
        validated_data.pop('clear_question_image', None)
        validated_data.pop('clear_option_a_image', None)
        validated_data.pop('clear_option_b_image', None)
        validated_data.pop('clear_option_c_image', None)
        validated_data.pop('clear_option_d_image', None)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        clear_question_image = validated_data.pop('clear_question_image', False)
        clear_option_a_image = validated_data.pop('clear_option_a_image', False)
        clear_option_b_image = validated_data.pop('clear_option_b_image', False)
        clear_option_c_image = validated_data.pop('clear_option_c_image', False)
        clear_option_d_image = validated_data.pop('clear_option_d_image', False)

        # Only clear when requested AND no replacement file was uploaded.
        if clear_question_image and 'question_image' not in validated_data:
            if instance.question_image:
                instance.question_image.delete(save=False)
            instance.question_image = None

        if clear_option_a_image and 'option_a_image' not in validated_data:
            if instance.option_a_image:
                instance.option_a_image.delete(save=False)
            instance.option_a_image = None

        if clear_option_b_image and 'option_b_image' not in validated_data:
            if instance.option_b_image:
                instance.option_b_image.delete(save=False)
            instance.option_b_image = None

        if clear_option_c_image and 'option_c_image' not in validated_data:
            if instance.option_c_image:
                instance.option_c_image.delete(save=False)
            instance.option_c_image = None

        if clear_option_d_image and 'option_d_image' not in validated_data:
            if instance.option_d_image:
                instance.option_d_image.delete(save=False)
            instance.option_d_image = None

        return super().update(instance, validated_data)

    def _question_for_validation(self, attrs, module=None):
        model_fields = {f.name for f in Question._meta.concrete_fields}
        q = Question()
        if self.instance is not None:
            for name in model_fields:
                setattr(q, name, getattr(self.instance, name))
        elif module is not None:
            # full_clean() raises "This field cannot be blank." for ForeignKey(blank=False)
            # even when null=True, so pre-populate the module to pass validation.
            q.module = module
            q.module_id = module.pk
        for key, val in attrs.items():
            if key in (
                "clear_question_image",
                "clear_option_a_image",
                "clear_option_b_image",
                "clear_option_c_image",
                "clear_option_d_image",
            ):
                continue
            model_key = "correct_answers" if key == "correct_answer" else key
            if model_key in model_fields:
                setattr(q, model_key, val)
        if attrs.get("clear_question_image") and "question_image" not in attrs:
            q.question_image = None
        if attrs.get("clear_option_a_image") and "option_a_image" not in attrs:
            q.option_a_image = None
        if attrs.get("clear_option_b_image") and "option_b_image" not in attrs:
            q.option_b_image = None
        if attrs.get("clear_option_c_image") and "option_c_image" not in attrs:
            q.option_c_image = None
        if attrs.get("clear_option_d_image") and "option_d_image" not in attrs:
            q.option_d_image = None
        return q

    def _raise_question_validation_error(self, exc):
        if hasattr(exc, "error_dict"):
            out = {}
            for key, msgs in exc.error_dict.items():
                if key == "correct_answers":
                    out["correct_answer"] = msgs
                elif key == NON_FIELD_ERRORS:
                    out[api_settings.NON_FIELD_ERRORS_KEY] = msgs
                else:
                    out[key] = msgs
            raise serializers.ValidationError(out)
        if hasattr(exc, "error_list"):
            raise serializers.ValidationError(
                {api_settings.NON_FIELD_ERRORS_KEY: list(exc.error_list)}
            )
        raise serializers.ValidationError(str(exc))

    def validate(self, attrs):
        attrs = super().validate(attrs)
        score = attrs.get("score")
        if self.instance is not None and score is None:
            score = self.instance.score
        if score is None:
            score = 10
        try:
            score = int(score)
        except (TypeError, ValueError):
            raise serializers.ValidationError({"score": "Invalid score."})
        attrs["score"] = score

        module = None
        if self.instance is not None:
            module = self.instance.module
        else:
            view = self.context.get("view")
            if view is not None and hasattr(view, "kwargs"):
                test_pk = view.kwargs.get("test_pk")
                module_pk = view.kwargs.get("module_pk")
                if test_pk and module_pk:
                    module = get_object_or_404(
                        Module, pk=module_pk, practice_test_id=test_pk
                    )

        if module is not None:
            pt = module.practice_test
            exam = getattr(pt, "mock_exam", None)
            if exam is None and pt.mock_exam_id:
                exam = MockExam.objects.filter(pk=pt.mock_exam_id).first()
            if exam is not None and exam.kind == MockExam.KIND_MIDTERM:
                # Midterms are graded as a percentage of the actual total (SCALE_100 =
                # correct/total × 100, weight-independent; SCALE_800 = proportional), so
                # there is no fixed total-points cap and per-question points are free —
                # only require a positive score.
                if score < 1:
                    raise serializers.ValidationError(
                        {"score": "Score must be at least 1."}
                    )

            # ── SAT question-type enforcement ─────────────────────────────
            # For full SAT simulations (pastpapers + mock exams), enforce that
            # question_type matches the section subject.  Midterms are exempt
            # (institution-controlled, flexible authoring).
            from .sat_rules import is_question_type_allowed, allowed_question_types_for_subject
            is_midterm = exam is not None and exam.kind == MockExam.KIND_MIDTERM
            if not is_midterm:
                q_type = attrs.get("question_type")
                if self.instance is not None and q_type is None:
                    q_type = self.instance.question_type
                subject = getattr(pt, "subject", None)
                if q_type and subject and not is_question_type_allowed(q_type, subject):
                    allowed = allowed_question_types_for_subject(subject)
                    subj_label = (
                        "Reading & Writing" if subject == "READING_WRITING" else "Math"
                    )
                    raise serializers.ValidationError(
                        {
                            "question_type": (
                                f"{subj_label} modules only allow question types: "
                                f"{', '.join(allowed)}. "
                                f"Got '{q_type}'."
                            )
                        }
                    )

        # Stub creation (POST with empty fields from admin "Add question") skips
        # content validation so a blank question can be saved and filled in later.
        is_stub = self.context.get('is_stub_create', False)
        if not is_stub:
            q = self._question_for_validation(attrs, module=module)
            try:
                # Skip unique/constraint checks: those depend on order+module assignment
                # which is resolved in perform_create/perform_update, not in validation.
                # We only want content validation (text, options, correct_answer format).
                q.full_clean(validate_unique=False, validate_constraints=False)
            except DjangoValidationError as e:
                self._raise_question_validation_error(e)
        return attrs


class AdminModuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Module
        fields = ['id', 'module_order', 'time_limit_minutes']

    def create(self, validated_data):
        test = self.context['test']
        return Module.objects.create(practice_test=test, **validated_data)


class AdminPracticeTestSerializer(serializers.ModelSerializer):
    modules = AdminModuleSerializer(many=True, read_only=True)
    subject = serializers.CharField()
    assigned_users = serializers.PrimaryKeyRelatedField(
        many=True, queryset=User.objects.all(), required=False
    )

    class Meta:
        model = PracticeTest
        fields = [
            "id",
            "title",
            "practice_date",
            "subject",
            "label",
            "form_type",
            "collection_name",
            "is_published",
            "published_at",
            "mock_exam",
            "modules",
            "assigned_users",
        ]
        read_only_fields = ["mock_exam", "published_at"]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Prefer model field — DB enum is always READING_WRITING | MATH when valid.
        v = getattr(instance, "subject", None)
        if v:
            canon = _normalize_platform_subject_value(v)
            if canon in ("MATH", "READING_WRITING"):
                data["subject"] = canon
            else:
                data["subject"] = str(v)
        return data

    def create(self, validated_data):
        assigned_users = validated_data.pop("assigned_users", [])
        inst = super().create(validated_data)
        if assigned_users:
            inst.assigned_users.set(assigned_users)
        return inst

    def update(self, instance, validated_data):
        assigned_users = validated_data.pop("assigned_users", serializers.empty)
        inst = super().update(instance, validated_data)
        if assigned_users is not serializers.empty:
            inst.assigned_users.set(assigned_users)
        return inst


class AdminPracticeTestPackSerializer(serializers.ModelSerializer):
    sections = AdminPracticeTestSerializer(many=True, read_only=True)
    section_count = serializers.SerializerMethodField()

    class Meta:
        model = PracticeTestPack
        fields = [
            "id",
            "title",
            "description",
            "is_published",
            "published_at",
            "created_by",
            "sections",
            "section_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "created_at", "updated_at", "published_at", "created_by",
        ]

    def get_section_count(self, obj) -> int:
        return obj.sections.count() if hasattr(obj, "sections") else 0


class AdminMockExamSerializer(serializers.ModelSerializer):
    tests = AdminPracticeTestSerializer(many=True, read_only=True)
    publish_ready = serializers.SerializerMethodField()
    publish_block_reason = serializers.SerializerMethodField()
    sat_violations = serializers.SerializerMethodField()

    class Meta:
        model = MockExam
        fields = [
            "id",
            "title",
            "practice_date",
            "is_active",
            "is_published",
            "published_at",
            "kind",
            "midterm_subject",
            "midterm_scoring_scale",
            "midterm_module_count",
            "midterm_module1_minutes",
            "midterm_module2_minutes",
            "midterm_target_question_count",
            "tests",
            "publish_ready",
            "publish_block_reason",
            "sat_violations",
        ]
        read_only_fields = [
            "is_published", "published_at",
            "publish_ready", "publish_block_reason", "sat_violations",
        ]

    def _get_violations(self, obj):
        cache_attr = "_sat_violations_cache"
        if not hasattr(obj, cache_attr):
            from .sat_rules import mock_exam_publish_violations
            setattr(obj, cache_attr, mock_exam_publish_violations(obj))
        return getattr(obj, cache_attr)

    def _publish_check(self, obj):
        violations = self._get_violations(obj)
        if violations:
            return False, violations[0].message
        return True, ""

    def get_publish_ready(self, obj):
        ok, _ = self._publish_check(obj)
        return ok

    def get_publish_block_reason(self, obj):
        ok, msg = self._publish_check(obj)
        return "" if ok else msg

    def get_sat_violations(self, obj) -> list[str]:
        return [v.message for v in self._get_violations(obj)]

    def validate(self, attrs):
        kind = attrs.get("kind", getattr(self.instance, "kind", MockExam.KIND_MOCK_SAT))
        if kind == MockExam.KIND_MIDTERM:
            mc = attrs.get(
                "midterm_module_count",
                getattr(self.instance, "midterm_module_count", 2) if self.instance else 2,
            )
            if mc not in (1, 2):
                raise serializers.ValidationError(
                    {"midterm_module_count": "Must be 1 or 2."}
                )
        return attrs


class BulkAssignmentDispatchSerializer(serializers.ModelSerializer):
    assigned_by_name = serializers.SerializerMethodField()

    class Meta:
        model = BulkAssignmentDispatch
        fields = [
            "id",
            "kind",
            "subject_summary",
            "students_requested_count",
            "students_granted_count",
            "assigned_by",
            "assigned_by_name",
            "status",
            "created_at",
        ]
        read_only_fields = fields

    def get_assigned_by_name(self, obj):
        u = obj.assigned_by
        if not u:
            return ""
        parts = [getattr(u, "first_name", None) or "", getattr(u, "last_name", None) or ""]
        name = " ".join(p for p in parts if p).strip()
        if name:
            return name
        return (getattr(u, "username", None) or getattr(u, "email", None) or "").strip() or f"User #{u.pk}"


class BulkAssignmentDispatchDetailSerializer(serializers.ModelSerializer):
    assigned_by_name = serializers.SerializerMethodField()
    skipped_users = serializers.SerializerMethodField()

    class Meta:
        model = BulkAssignmentDispatch
        fields = [
            "id",
            "kind",
            "subject_summary",
            "students_requested_count",
            "students_granted_count",
            "assigned_by",
            "assigned_by_name",
            "status",
            "payload",
            "result",
            "rerun_of",
            "created_at",
            "actor_snapshot",
            "skipped_users",
        ]
        read_only_fields = fields

    def get_assigned_by_name(self, obj):
        return BulkAssignmentDispatchSerializer().get_assigned_by_name(obj)

    def get_skipped_users(self, obj):
        res = obj.result or {}
        val = res.get("skipped_users") if isinstance(res, dict) else []
        return val or []
