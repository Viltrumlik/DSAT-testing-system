from __future__ import annotations

from drf_spectacular.utils import extend_schema_serializer
from rest_framework import serializers

from .models import (
    AssessmentSet,
    AssessmentSetVersion,
    AssessmentQuestion,
    HomeworkAssignment,
    AssessmentAttempt,
    AssessmentAnswer,
    AssessmentResult,
)


@extend_schema_serializer(component_name="AssessmentQuestion")
class AssessmentQuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssessmentQuestion
        fields = [
            "id",
            "order",
            "prompt",
            "question_prompt",
            "question_type",
            "choices",
            "points",
            "is_active",
            "explanation",
            "question_image",
            "option_a_image",
            "option_b_image",
            "option_c_image",
            "option_d_image",
        ]


class AssessmentQuestionAdminReadSerializer(serializers.ModelSerializer):
    """
    Admin-only read serializer: identical to AssessmentQuestionSerializer but
    also exposes correct_answer and grading_config so the builder UI can
    correctly display the saved correct answer when re-opening a question.
    NOT used on student-facing endpoints.
    """

    class Meta:
        model = AssessmentQuestion
        fields = [
            "id",
            "order",
            "prompt",
            "question_prompt",
            "question_type",
            "choices",
            "correct_answer",
            "grading_config",
            "points",
            "is_active",
            "explanation",
            "question_image",
            "option_a_image",
            "option_b_image",
            "option_c_image",
            "option_d_image",
        ]


class AssessmentQuestionAdminWriteSerializer(serializers.ModelSerializer):
    clear_question_image = serializers.BooleanField(write_only=True, required=False)
    clear_option_a_image = serializers.BooleanField(write_only=True, required=False)
    clear_option_b_image = serializers.BooleanField(write_only=True, required=False)
    clear_option_c_image = serializers.BooleanField(write_only=True, required=False)
    clear_option_d_image = serializers.BooleanField(write_only=True, required=False)

    class Meta:
        model = AssessmentQuestion
        fields = [
            "id",
            "assessment_set",
            "order",
            "prompt",
            "question_prompt",
            "question_type",
            "choices",
            "correct_answer",
            "grading_config",
            "points",
            "is_active",
            "explanation",
            "question_image",
            "option_a_image",
            "option_b_image",
            "option_c_image",
            "option_d_image",
            "clear_question_image",
            "clear_option_a_image",
            "clear_option_b_image",
            "clear_option_c_image",
            "clear_option_d_image",
        ]

    def _clear_image_field(self, instance, field_name):
        field = getattr(instance, field_name)
        if field:
            field.delete(save=False)
        setattr(instance, field_name, None)

    def create(self, validated_data):
        for key in ["clear_question_image", "clear_option_a_image", "clear_option_b_image",
                    "clear_option_c_image", "clear_option_d_image"]:
            validated_data.pop(key, None)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        image_fields = {
            "question_image": validated_data.pop("clear_question_image", False),
            "option_a_image": validated_data.pop("clear_option_a_image", False),
            "option_b_image": validated_data.pop("clear_option_b_image", False),
            "option_c_image": validated_data.pop("clear_option_c_image", False),
            "option_d_image": validated_data.pop("clear_option_d_image", False),
        }
        for field_name, should_clear in image_fields.items():
            if should_clear and field_name not in validated_data:
                self._clear_image_field(instance, field_name)
        return super().update(instance, validated_data)


@extend_schema_serializer(component_name="AssessmentSet")
class AssessmentSetSerializer(serializers.ModelSerializer):
    questions = AssessmentQuestionSerializer(many=True, read_only=True)

    class Meta:
        model = AssessmentSet
        fields = [
            "id",
            "subject",
            "category",
            "title",
            "description",
            "is_active",
            "created_at",
            "updated_at",
            "questions",
        ]


@extend_schema_serializer(component_name="AssessmentSetAdmin")
class AssessmentSetAdminSerializer(serializers.ModelSerializer):
    """
    Admin read serializer for a set: includes correct_answer + grading_config
    on each question so the builder UI can display saved answers correctly.
    Only used by admin endpoints — never exposed to students.
    """

    questions = AssessmentQuestionAdminReadSerializer(many=True, read_only=True)

    class Meta:
        model = AssessmentSet
        fields = [
            "id",
            "subject",
            "category",
            "title",
            "description",
            "is_active",
            "created_at",
            "updated_at",
            "questions",
        ]


class AssessmentSetAdminWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssessmentSet
        fields = [
            "id",
            "subject",
            "category",
            "title",
            "description",
            "is_active",
        ]


class HomeworkAssignmentSerializer(serializers.ModelSerializer):
    assessment_set = AssessmentSetSerializer(read_only=True)

    class Meta:
        model = HomeworkAssignment
        fields = ["id", "classroom_id", "assignment_id", "assessment_set", "assigned_by_id", "created_at"]


@extend_schema_serializer(component_name="AssessmentAttemptAnswer")
class AttemptAnswerSerializer(serializers.ModelSerializer):
    question_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = AssessmentAnswer
        fields = [
            "id",
            "question_id",
            "answer",
            "time_spent_seconds",
            "is_correct",
            "points_awarded",
            "answered_at",
        ]


@extend_schema_serializer(component_name="AssessmentAttempt")
class AttemptSerializer(serializers.ModelSerializer):
    answers = AttemptAnswerSerializer(many=True, read_only=True)
    homework_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = AssessmentAttempt
        fields = [
            "id",
            "homework_id",
            "student_id",
            "status",
            "started_at",
            "submitted_at",
            "abandoned_at",
            "last_activity_at",
            "total_time_seconds",
            "active_time_seconds",
            "question_times",
            "grading_status",
            "grading_attempts",
            "question_order",
            "answers",
        ]


@extend_schema_serializer(component_name="AssessmentResult")
class ResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssessmentResult
        fields = [
            "id",
            "attempt_id",
            "score_points",
            "max_points",
            "percent",
            "correct_count",
            "total_questions",
            "graded_at",
        ]


class AssignHomeworkSerializer(serializers.Serializer):
    classroom_id = serializers.IntegerField()
    set_id = serializers.IntegerField()
    title = serializers.CharField(required=False, allow_blank=True)
    instructions = serializers.CharField(required=False, allow_blank=True)
    due_at = serializers.DateTimeField(required=False, allow_null=True)


class StartAttemptSerializer(serializers.Serializer):
    assignment_id = serializers.IntegerField()
    # Optional: retry mode — restrict attempt to a subset of question IDs.
    # Used by "retry incorrect only" flow in the pedagogical review page.
    focus_question_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
        allow_empty=True,
        max_length=500,
    )


class SaveAnswerSerializer(serializers.Serializer):
    attempt_id = serializers.IntegerField()
    question_id = serializers.IntegerField()
    answer = serializers.JSONField(required=False, allow_null=True)
    client_seq = serializers.IntegerField(required=False, min_value=0)
    # Client may send these, but server will ignore for time tracking.
    answered_at = serializers.DateTimeField(required=False)


class SubmitAttemptSerializer(serializers.Serializer):
    attempt_id = serializers.IntegerField()


class ApiAssessmentDetailSerializer(serializers.Serializer):
    """Minimal `{detail}` error payloads returned by assessments student APIs."""

    detail = serializers.CharField()


class SaveAnswerStaleWriteSerializer(serializers.Serializer):
    detail = serializers.CharField()
    code = serializers.CharField()
    server_client_seq = serializers.IntegerField()
    answer_id = serializers.IntegerField()


class SaveAnswerStoredSerializer(serializers.Serializer):
    answer_id = serializers.IntegerField()


@extend_schema_serializer(component_name="AssessmentAttemptBundleResponse")
class AttemptBundleResponseSerializer(serializers.Serializer):
    attempt = AttemptSerializer()
    set = AssessmentSetSerializer()
    questions = AssessmentQuestionSerializer(many=True)


@extend_schema_serializer(component_name="AssessmentSubmitQueuedResponse")
class SubmitAttemptQueuedResponseSerializer(serializers.Serializer):
    """Async grading accepted; poll `my-result` or re-fetch bundle for graded state."""

    attempt = AttemptSerializer()
    result = ResultSerializer(required=True, allow_null=True)
    grading = serializers.ChoiceField(choices=[("pending", "Pending")])


@extend_schema_serializer(component_name="AssessmentSubmitCompleteResponse")
class SubmitAttemptCompleteResponseSerializer(serializers.Serializer):
    """Submit completed synchronously or idempotent replay of submitted/graded attempt."""

    attempt = AttemptSerializer()
    result = ResultSerializer(required=False, allow_null=True)


@extend_schema_serializer(component_name="AssessmentSnapshotConflictResponse")
class SubmitAssessmentVersionConflictSerializer(serializers.Serializer):
    detail = serializers.CharField()


@extend_schema_serializer(component_name="AssessmentSubmitBadRequestResponse")
class SubmitAttemptBadRequestSerializer(serializers.Serializer):
    detail = serializers.CharField()
    missing_question_ids = serializers.ListField(child=serializers.IntegerField(), required=False)


@extend_schema_serializer(component_name="AssessmentMyResultResponse")
class MyAssessmentResultResponseSerializer(serializers.Serializer):
    attempt = AttemptSerializer(required=True, allow_null=True)
    result = ResultSerializer(required=True, allow_null=True)


@extend_schema_serializer(component_name="AssessmentSetVersion")
class AssessmentSetVersionSerializer(serializers.ModelSerializer):
    """
    Read-only serializer for AssessmentSetVersion.

    snapshot_json is intentionally excluded from the default fields — it is
    large and should only be returned when explicitly requested (e.g. a
    dedicated snapshot-download endpoint). Use snapshot_json_field below
    if you need to include it.
    """

    set_id = serializers.IntegerField(source="assessment_set_id", read_only=True)
    set_title = serializers.CharField(source="assessment_set.title", read_only=True)
    published_by_email = serializers.SerializerMethodField()

    class Meta:
        model = AssessmentSetVersion
        fields = [
            "id",
            "set_id",
            "set_title",
            "version_number",
            "snapshot_checksum",
            "question_count",
            "published_by",
            "published_by_email",
            "published_at",
        ]
        read_only_fields = fields

    def get_published_by_email(self, obj) -> str | None:
        if obj.published_by_id is None:
            return None
        return getattr(obj.published_by, "email", None)


@extend_schema_serializer(component_name="AdminPublishResponse")
class AdminPublishResponseSerializer(serializers.Serializer):
    """Returned by POST /admin/sets/{pk}/publish/."""

    version = AssessmentSetVersionSerializer(read_only=True)
    created = serializers.BooleanField(
        read_only=True,
        help_text="True = new version was created; False = identical content, existing version returned.",
    )

