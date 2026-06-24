"""Read-only serializers for the Question Bank admin API (Phase A).

Pure exposure layer — no writes. The AI triage suggestion is surfaced as a nested
``suggestion`` object that ALWAYS carries ``advisory: true`` and is never presented
as applied taxonomy: human classification stays mandatory (see triage.py).

Image fields are emitted as RELATIVE media URLs (e.g. ``/media/question_bank/...``)
to match the assessments convention; the frontend prepends the origin.
"""
from __future__ import annotations

from rest_framework import serializers

import json

from django.db.models import Count

from .models import (
    BankDomain,
    BankPassage,
    BankQuestion,
    BankQuestionVersion,
    BankSkill,
    Difficulty,
    ImportBatch,
    ImportCandidate,
    QuestionStatus,
)
from .services import create_bank_question, update_bank_question


def _image_url(field) -> str | None:
    """Relative media URL for an ImageField, or None when unset/missing."""
    try:
        return field.url if field else None
    except ValueError:
        return None


def _suggestion_payload(obj: BankQuestion, *, detail: bool) -> dict | None:
    """Advisory triage suggestion. Returns None when nothing was suggested.

    NEVER mirrors applied taxonomy — ``advisory: true`` is always present so the
    UI cannot mistake a hint for a human-approved classification.
    """
    has_any = bool(
        obj.suggested_domain_id
        or obj.suggested_skill_id
        or obj.suggested_difficulty
        or obj.suggestion_rationale
    )
    if not has_any:
        return None
    data: dict = {
        "advisory": True,
        "domain": (
            {"id": obj.suggested_domain_id, "name": obj.suggested_domain.name}
            if obj.suggested_domain_id
            else None
        ),
        "skill": (
            {"id": obj.suggested_skill_id, "name": obj.suggested_skill.name}
            if obj.suggested_skill_id
            else None
        ),
        "difficulty": obj.suggested_difficulty or None,
        "confidence": obj.suggestion_confidence,
    }
    if detail:
        data["model"] = obj.suggestion_model or None
        data["rationale"] = obj.suggestion_rationale or None
    return data


# ── Taxonomy ──────────────────────────────────────────────────────────────────
class BankDomainSerializer(serializers.ModelSerializer):
    class Meta:
        model = BankDomain
        fields = ["id", "subject", "name", "code", "display_order"]


class BankSkillSerializer(serializers.ModelSerializer):
    subject = serializers.CharField(source="domain.subject", read_only=True)
    domain_name = serializers.CharField(source="domain.name", read_only=True)

    class Meta:
        model = BankSkill
        fields = ["id", "domain", "domain_name", "subject", "name", "code", "display_order"]


# ── Passage ───────────────────────────────────────────────────────────────────
class BankPassageSerializer(serializers.ModelSerializer):
    question_count = serializers.IntegerField(source="questions.count", read_only=True)

    class Meta:
        model = BankPassage
        fields = [
            "id", "subject", "passage_text", "content_hash",
            "source_type", "source_reference", "import_batch",
            "metadata", "question_count", "created_at", "updated_at",
        ]


# ── Questions ─────────────────────────────────────────────────────────────────
class BankQuestionListSerializer(serializers.ModelSerializer):
    """Compact row for the browsing/triage tables."""

    domain_name = serializers.CharField(source="domain.name", read_only=True, default=None)
    skill_name = serializers.CharField(source="skill.name", read_only=True, default=None)
    has_image = serializers.SerializerMethodField()
    suggestion = serializers.SerializerMethodField()

    class Meta:
        model = BankQuestion
        fields = [
            "id", "qb_id", "external_id", "subject", "status", "question_type", "difficulty",
            "domain", "domain_name", "skill", "skill_name",
            "question_text", "passage", "has_image",
            "source_type", "content_hash", "import_batch",
            "suggestion", "created_at", "updated_at",
        ]

    def get_has_image(self, obj) -> bool:
        return bool(
            obj.question_image
            or obj.option_a_image
            or obj.option_b_image
            or obj.option_c_image
            or obj.option_d_image
        )

    def get_suggestion(self, obj):
        return _suggestion_payload(obj, detail=False)


class BankQuestionDetailSerializer(serializers.ModelSerializer):
    """Full question for the detail screen (Preview / Details tabs)."""

    domain = BankDomainSerializer(read_only=True)
    skill = BankSkillSerializer(read_only=True)
    passage = BankPassageSerializer(read_only=True)
    question_image = serializers.SerializerMethodField()
    option_a_image = serializers.SerializerMethodField()
    option_b_image = serializers.SerializerMethodField()
    option_c_image = serializers.SerializerMethodField()
    option_d_image = serializers.SerializerMethodField()
    current_version_number = serializers.IntegerField(
        source="current_version.version_number", read_only=True, default=None
    )
    version_count = serializers.IntegerField(source="versions.count", read_only=True)
    # Reuse signal: how many assessment questions link back to this bank question.
    assessment_usage_count = serializers.IntegerField(
        source="assessment_questions.count", read_only=True
    )
    suggestion = serializers.SerializerMethodField()

    class Meta:
        model = BankQuestion
        fields = [
            "id", "qb_id", "external_id", "subject", "status", "question_type", "difficulty",
            "domain", "skill", "passage",
            "question_text", "question_prompt", "question_image",
            "option_a", "option_b", "option_c", "option_d",
            "option_a_image", "option_b_image", "option_c_image", "option_d_image",
            "correct_answer", "student_answer", "explanation", "points",
            "content_hash", "source_type", "source_reference", "import_batch",
            "current_version_number", "version_count", "assessment_usage_count",
            "suggestion", "metadata", "created_at", "updated_at",
        ]

    def get_question_image(self, obj):
        return _image_url(obj.question_image)

    def get_option_a_image(self, obj):
        return _image_url(obj.option_a_image)

    def get_option_b_image(self, obj):
        return _image_url(obj.option_b_image)

    def get_option_c_image(self, obj):
        return _image_url(obj.option_c_image)

    def get_option_d_image(self, obj):
        return _image_url(obj.option_d_image)

    def get_suggestion(self, obj):
        return _suggestion_payload(obj, detail=True)


# ── Versions ──────────────────────────────────────────────────────────────────
# ── Student practice (APPROVED-only; NEVER leaks correct_answer/explanation) ───
def _has_any_image(q: BankQuestion) -> bool:
    return bool(
        q.question_image or q.option_a_image or q.option_b_image
        or q.option_c_image or q.option_d_image
    )


class PracticeQuestionListSerializer(serializers.ModelSerializer):
    domain_name = serializers.CharField(source="domain.name", read_only=True, default=None)
    skill_name = serializers.CharField(source="skill.name", read_only=True, default=None)
    has_image = serializers.SerializerMethodField()

    class Meta:
        model = BankQuestion
        fields = [
            "id", "qb_id", "subject", "question_type", "difficulty",
            "domain_name", "skill_name", "question_text", "has_image",
        ]

    def get_has_image(self, obj) -> bool:
        return _has_any_image(obj)


class PracticeQuestionDetailSerializer(serializers.ModelSerializer):
    """Renderable question for self-study — deliberately WITHOUT correct_answer,
    explanation, or student_answer (those arrive only after the student answers)."""

    domain_name = serializers.CharField(source="domain.name", read_only=True, default=None)
    skill_name = serializers.CharField(source="skill.name", read_only=True, default=None)
    passage_text = serializers.CharField(source="passage.passage_text", read_only=True, default=None)
    question_image = serializers.SerializerMethodField()
    choices = serializers.SerializerMethodField()

    class Meta:
        model = BankQuestion
        fields = [
            "id", "qb_id", "subject", "question_type", "difficulty",
            "domain_name", "skill_name", "passage_text",
            "question_text", "question_prompt", "question_image", "choices", "points",
        ]

    def get_question_image(self, obj):
        return _image_url(obj.question_image)

    def get_choices(self, obj) -> list[dict]:
        out = []
        for letter in ("a", "b", "c", "d"):
            text = getattr(obj, f"option_{letter}")
            image = _image_url(getattr(obj, f"option_{letter}_image"))
            if (text or "").strip() or image:
                out.append({"id": letter.upper(), "text": text, "image": image})
        return out


class FlexibleJSONField(serializers.JSONField):
    """Accepts a JSON value OR a bare string (multipart sends "C", not '"C"')."""

    def to_internal_value(self, data):
        if isinstance(data, str):
            try:
                return json.loads(data)
            except (ValueError, TypeError):
                return data  # plain answer like "C" or "2/3"
        return data


_CLEAR_IMAGE_MAP = {
    "clear_question_image": "question_image",
    "clear_option_a_image": "option_a_image",
    "clear_option_b_image": "option_b_image",
    "clear_option_c_image": "option_c_image",
    "clear_option_d_image": "option_d_image",
}


class BankQuestionWriteSerializer(serializers.ModelSerializer):
    """Create/edit a bank question (multipart for images). Delegates to services so
    content_hash + versioning always move together. Status is NOT set here —
    transitions go through the triage endpoints; create lands in TRIAGE."""

    domain = serializers.PrimaryKeyRelatedField(
        queryset=BankDomain.objects.all(), required=False, allow_null=True
    )
    skill = serializers.PrimaryKeyRelatedField(
        queryset=BankSkill.objects.all(), required=False, allow_null=True
    )
    correct_answer = FlexibleJSONField(required=False, allow_null=True)
    student_answer = FlexibleJSONField(required=False, allow_null=True)
    clear_question_image = serializers.BooleanField(write_only=True, required=False, default=False)
    clear_option_a_image = serializers.BooleanField(write_only=True, required=False, default=False)
    clear_option_b_image = serializers.BooleanField(write_only=True, required=False, default=False)
    clear_option_c_image = serializers.BooleanField(write_only=True, required=False, default=False)
    clear_option_d_image = serializers.BooleanField(write_only=True, required=False, default=False)

    class Meta:
        model = BankQuestion
        fields = [
            "subject", "question_type", "difficulty", "external_id",
            "domain", "skill",
            "question_text", "question_prompt", "question_image",
            "option_a", "option_b", "option_c", "option_d",
            "option_a_image", "option_b_image", "option_c_image", "option_d_image",
            "correct_answer", "student_answer", "explanation", "points",
            *(_CLEAR_IMAGE_MAP.keys()),
        ]
        extra_kwargs = {
            "subject": {"required": False},
            "question_type": {"required": False},
            "question_text": {"required": False, "allow_blank": True},
        }

    def validate(self, attrs):
        inst = self.instance
        subject = attrs.get("subject") or (inst.subject if inst else None)
        domain = attrs.get("domain", inst.domain if inst else None)
        skill = attrs.get("skill", inst.skill if inst else None)
        if domain is not None and subject and domain.subject != subject:
            raise serializers.ValidationError({"domain": f"Domain is not in subject {subject}."})
        if skill is not None:
            if domain is None:
                raise serializers.ValidationError({"skill": "Choose a domain before a skill."})
            if skill.domain_id != domain.id:
                raise serializers.ValidationError({"skill": "Skill does not belong to the domain."})
        return attrs

    def _apply_clears(self, validated):
        for flag, field in _CLEAR_IMAGE_MAP.items():
            do_clear = validated.pop(flag, False)
            if do_clear and field not in validated:  # a fresh upload wins over clear
                validated[field] = None

    @property
    def _actor(self):
        request = self.context.get("request")
        return getattr(request, "user", None)

    def create(self, validated):
        self._apply_clears(validated)
        subject = validated.pop("subject", None)
        question_type = validated.pop("question_type", None)
        question_text = validated.pop("question_text", "")
        if not subject:
            raise serializers.ValidationError({"subject": "Required."})
        if not question_type:
            raise serializers.ValidationError({"question_type": "Required."})
        return create_bank_question(
            subject=subject, question_type=question_type, question_text=question_text,
            status=QuestionStatus.TRIAGE, user=self._actor, **validated,
        )

    def update(self, instance, validated):
        self._apply_clears(validated)
        return update_bank_question(instance, user=self._actor, **validated)


class BankQuestionVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = BankQuestionVersion
        fields = [
            "id", "bank_question", "version_number", "snapshot_checksum",
            "previous_version", "created_by", "created_at",
        ]


class BankQuestionVersionDetailSerializer(BankQuestionVersionSerializer):
    """Adds the immutable snapshot payload (opt-in via ?include_snapshot=true)."""

    class Meta(BankQuestionVersionSerializer.Meta):
        fields = BankQuestionVersionSerializer.Meta.fields + ["snapshot_json"]


# ── Triage write inputs (Phase B) ─────────────────────────────────────────────
class TriageClassifyInputSerializer(serializers.Serializer):
    domain = serializers.PrimaryKeyRelatedField(queryset=BankDomain.objects.all())
    skill = serializers.PrimaryKeyRelatedField(queryset=BankSkill.objects.all())
    difficulty = serializers.ChoiceField(choices=Difficulty.choices)


class TriageRejectInputSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, default="")


class BulkTriageInputSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["approve", "reject", "classify"])
    ids = serializers.ListField(child=serializers.IntegerField(), allow_empty=False)
    # classify-only
    domain = serializers.PrimaryKeyRelatedField(queryset=BankDomain.objects.all(), required=False)
    skill = serializers.PrimaryKeyRelatedField(queryset=BankSkill.objects.all(), required=False)
    difficulty = serializers.ChoiceField(choices=Difficulty.choices, required=False)
    # reject-only
    reason = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs):
        if attrs["action"] == "classify":
            missing = [f for f in ("domain", "skill", "difficulty") if attrs.get(f) in (None, "")]
            if missing:
                raise serializers.ValidationError(
                    {f: "Required for action=classify." for f in missing}
                )
        return attrs


# ── Import batches (Phase B) ──────────────────────────────────────────────────
_BATCH_STATUS_LABELS = {
    ImportBatch.Status.PENDING: "Uploaded",
    ImportBatch.Status.PARSING: "Processing",
    ImportBatch.Status.READY: "Ready For Review",
    ImportBatch.Status.PROMOTED: "Imported",
    ImportBatch.Status.FAILED: "Validation Failed",
}


class ImportBatchSerializer(serializers.ModelSerializer):
    status_display = serializers.SerializerMethodField()
    candidate_counts = serializers.SerializerMethodField()

    class Meta:
        model = ImportBatch
        fields = [
            "id", "source_type", "filename", "source_reference",
            "status", "status_display", "total_candidates", "promoted_count",
            "candidate_counts", "notes", "created_at", "updated_at",
        ]

    def _counts(self, obj) -> dict:
        if not hasattr(obj, "_qb_counts"):
            obj._qb_counts = {
                row["validation_status"]: row["n"]
                for row in obj.candidates.values("validation_status").annotate(n=Count("id"))
            }
        return obj._qb_counts

    def get_candidate_counts(self, obj) -> dict:
        c = self._counts(obj)
        V = ImportCandidate.Validation
        return {
            "valid": c.get(V.VALID, 0),
            "warning": c.get(V.WARNING, 0),
            "error": c.get(V.ERROR, 0),
            "duplicate": c.get(V.DUPLICATE, 0),
        }

    def get_status_display(self, obj) -> str:
        # READY but carrying parse errors surfaces as "Validation Failed".
        if obj.status == ImportBatch.Status.READY and self._counts(obj).get(
            ImportCandidate.Validation.ERROR, 0
        ):
            return "Validation Failed"
        return _BATCH_STATUS_LABELS.get(obj.status, obj.status)


class ImportCandidateSerializer(serializers.ModelSerializer):
    duplicate_of_qb_id = serializers.CharField(source="duplicate_of.qb_id", read_only=True, default=None)
    promoted_question_qb_id = serializers.CharField(source="promoted_question.qb_id", read_only=True, default=None)

    class Meta:
        model = ImportCandidate
        fields = [
            "id", "batch", "order", "subject", "external_id",
            "raw_domain", "raw_skill", "raw_difficulty",
            "passage_text", "question_text",
            "option_a", "option_b", "option_c", "option_d",
            "correct_answer", "student_answer", "question_image",
            "explanation", "content_hash",
            "page_start", "page_end",
            "validation_status", "validation_messages",
            "duplicate_of", "duplicate_of_qb_id",
            "promoted_question", "promoted_question_qb_id",
            "created_at",
        ]
