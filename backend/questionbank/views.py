"""Read-only Question Bank admin API (Phase A).

Exposure over the existing ``questionbank`` models for the admin browsing UI.
No writes here — triage/import mutations live in their own milestone. Auth gate is
global-staff-only (``CanManageQuestions``); ``IsAuthenticatedAndNotFrozen`` is the
project default but is listed explicitly for clarity.
"""
from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, status as http_status
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from access.permissions import CanManageQuestions
from users.permissions import IsAuthenticatedAndNotFrozen

from . import audit, serializers as qb, triage
from .import_pipeline import promote_batch

# Parsers for content authoring (images via multipart; JSON also accepted).
_WRITE_PARSERS = [MultiPartParser, FormParser, JSONParser]
from .models import (
    BankDomain,
    BankPassage,
    BankQuestion,
    BankQuestionAttempt,
    BankQuestionVersion,
    BankSkill,
    ImportBatch,
    ImportCandidate,
)
from .triage import TriageError

QB_PERMISSIONS = [IsAuthenticatedAndNotFrozen, CanManageQuestions]

_TRUTHY = {"1", "true", "yes", "on"}


def _truthy(raw) -> bool:
    return str(raw or "").strip().lower() in _TRUTHY


def _int_or_none(raw):
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


class QbPagination(LimitOffsetPagination):
    """Project has no global PAGE_SIZE, so plain LimitOffset would return an
    unwrapped list; this gives a paginated envelope with sane bounds."""

    default_limit = 50
    max_limit = 200


@extend_schema(tags=["questionbank"])
class BankQuestionListView(generics.ListCreateAPIView):
    """GET /api/questionbank/questions/ — filter/search; POST — author a new question."""

    permission_classes = QB_PERMISSIONS
    pagination_class = QbPagination
    parser_classes = _WRITE_PARSERS

    def get_serializer_class(self):
        if self.request.method == "POST":
            return qb.BankQuestionWriteSerializer
        return qb.BankQuestionListSerializer

    def create(self, request, *args, **kwargs):
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            question = ser.save()
        except DjangoValidationError as exc:
            return Response({"detail": exc.messages}, status=http_status.HTTP_400_BAD_REQUEST)
        audit.record_question_event(
            event_type=audit.EVT_CREATE, question=question, actor=request.user,
            previous_state="", new_state=question.status,
        )
        return Response(qb.BankQuestionDetailSerializer(question).data, status=http_status.HTTP_201_CREATED)

    def get_queryset(self):
        qs = BankQuestion.objects.select_related(
            "domain", "skill", "passage", "import_batch",
            "suggested_domain", "suggested_skill",
        )
        p = self.request.query_params
        if p.get("subject"):
            qs = qs.filter(subject=p["subject"])
        if p.get("status"):
            qs = qs.filter(status=p["status"])
        if p.get("difficulty"):
            qs = qs.filter(difficulty=p["difficulty"])
        source = p.get("source") or p.get("source_type")
        if source:
            qs = qs.filter(source_type=source)
        if (domain_id := _int_or_none(p.get("domain"))) is not None:
            qs = qs.filter(domain_id=domain_id)
        if (skill_id := _int_or_none(p.get("skill"))) is not None:
            qs = qs.filter(skill_id=skill_id)
        if (batch_id := _int_or_none(p.get("import_batch"))) is not None:
            qs = qs.filter(import_batch_id=batch_id)
        term = (p.get("search") or p.get("q") or "").strip()
        if term:
            qs = qs.filter(
                Q(qb_id__icontains=term)
                | Q(external_id__icontains=term)
                | Q(question_text__icontains=term)
            )
        return qs.order_by("-created_at", "-id")


@extend_schema(tags=["questionbank"])
class BankQuestionDetailView(generics.RetrieveUpdateAPIView):
    """GET /api/questionbank/questions/<id>/ ; PATCH — edit (any status; cuts a version)."""

    permission_classes = QB_PERMISSIONS
    parser_classes = _WRITE_PARSERS
    queryset = BankQuestion.objects.select_related(
        "domain", "skill", "passage", "import_batch",
        "suggested_domain", "suggested_skill", "current_version",
    )

    def get_serializer_class(self):
        if self.request.method in ("PATCH", "PUT"):
            return qb.BankQuestionWriteSerializer
        return qb.BankQuestionDetailSerializer

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        prev = instance.status
        ser = self.get_serializer(instance, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        try:
            question = ser.save()
        except DjangoValidationError as exc:
            return Response({"detail": exc.messages}, status=http_status.HTTP_400_BAD_REQUEST)
        audit.record_question_event(
            event_type=audit.EVT_UPDATE, question=question, actor=request.user,
            previous_state=prev, new_state=question.status,
        )
        return Response(qb.BankQuestionDetailSerializer(question).data)


@extend_schema(tags=["questionbank"])
class BankQuestionArchiveView(APIView):
    """POST /api/questionbank/questions/<id>/archive/ — soft-delete (reversible)."""

    permission_classes = QB_PERMISSIONS

    def post(self, request, pk):
        question = get_object_or_404(BankQuestion, pk=pk)
        prev = question.status
        with transaction.atomic():
            triage.archive_question(question, user=request.user)
            audit.record_question_event(
                event_type=audit.EVT_ARCHIVE, question=question, actor=request.user,
                previous_state=prev, new_state=question.status,
            )
        return _question_response(question)


@extend_schema(tags=["questionbank"])
class BankQuestionRestoreView(APIView):
    """POST /api/questionbank/questions/<id>/restore/ — un-archive."""

    permission_classes = QB_PERMISSIONS

    def post(self, request, pk):
        question = get_object_or_404(BankQuestion, pk=pk)
        prev = question.status
        with transaction.atomic():
            triage.restore_question(question, user=request.user)
            audit.record_question_event(
                event_type=audit.EVT_RESTORE, question=question, actor=request.user,
                previous_state=prev, new_state=question.status,
            )
        return _question_response(question)


@extend_schema(tags=["questionbank"])
class BankPassageListView(generics.ListAPIView):
    """GET /api/questionbank/passages/."""

    permission_classes = QB_PERMISSIONS
    serializer_class = qb.BankPassageSerializer
    pagination_class = QbPagination

    def get_queryset(self):
        qs = BankPassage.objects.all()
        p = self.request.query_params
        if p.get("subject"):
            qs = qs.filter(subject=p["subject"])
        if (batch_id := _int_or_none(p.get("import_batch"))) is not None:
            qs = qs.filter(import_batch_id=batch_id)
        term = (p.get("search") or p.get("q") or "").strip()
        if term:
            qs = qs.filter(passage_text__icontains=term)
        return qs.order_by("-created_at", "-id")


@extend_schema(tags=["questionbank"])
class BankPassageDetailView(generics.RetrieveAPIView):
    """GET /api/questionbank/passages/<id>/."""

    permission_classes = QB_PERMISSIONS
    serializer_class = qb.BankPassageSerializer
    queryset = BankPassage.objects.all()


@extend_schema(
    tags=["questionbank"],
    parameters=[
        OpenApiParameter("bank_question", int, description="Filter to one question's lineage."),
        OpenApiParameter("include_snapshot", bool, description="Include immutable snapshot_json."),
    ],
)
class BankQuestionVersionListView(generics.ListAPIView):
    """GET /api/questionbank/versions/ — append-only version lineage."""

    permission_classes = QB_PERMISSIONS
    pagination_class = QbPagination

    def get_serializer_class(self):
        if _truthy(self.request.query_params.get("include_snapshot")):
            return qb.BankQuestionVersionDetailSerializer
        return qb.BankQuestionVersionSerializer

    def get_queryset(self):
        qs = BankQuestionVersion.objects.all()
        if (bq_id := _int_or_none(self.request.query_params.get("bank_question"))) is not None:
            qs = qs.filter(bank_question_id=bq_id)
        return qs.order_by("bank_question_id", "-version_number")


@extend_schema(tags=["questionbank"], parameters=[OpenApiParameter("subject", str)])
class BankDomainListView(generics.ListAPIView):
    """GET /api/questionbank/domains/ — unpaginated taxonomy for filter dropdowns."""

    permission_classes = QB_PERMISSIONS
    serializer_class = qb.BankDomainSerializer
    pagination_class = None

    def get_queryset(self):
        qs = BankDomain.objects.all()
        if self.request.query_params.get("subject"):
            qs = qs.filter(subject=self.request.query_params["subject"])
        return qs.order_by("subject", "display_order", "name")


@extend_schema(
    tags=["questionbank"],
    parameters=[OpenApiParameter("domain", int), OpenApiParameter("subject", str)],
)
class BankSkillListView(generics.ListAPIView):
    """GET /api/questionbank/skills/ — unpaginated; filter by domain or subject."""

    permission_classes = QB_PERMISSIONS
    serializer_class = qb.BankSkillSerializer
    pagination_class = None

    def get_queryset(self):
        qs = BankSkill.objects.select_related("domain")
        p = self.request.query_params
        if (domain_id := _int_or_none(p.get("domain"))) is not None:
            qs = qs.filter(domain_id=domain_id)
        if p.get("subject"):
            qs = qs.filter(domain__subject=p["subject"])
        return qs.order_by("domain__display_order", "display_order", "name")


# ══════════════════════════════════════════════════════════════════════════════
# Triage write API (Phase B) — wraps triage.py; audit iff committed.
# ══════════════════════════════════════════════════════════════════════════════
def _question_response(question: BankQuestion) -> Response:
    return Response(qb.BankQuestionDetailSerializer(question).data)


@extend_schema(tags=["questionbank"])
class BankQuestionClassifyView(APIView):
    """POST /api/questionbank/questions/<id>/classify/ — assign real taxonomy."""

    permission_classes = QB_PERMISSIONS

    def post(self, request, pk):
        question = get_object_or_404(BankQuestion, pk=pk)
        data = qb.TriageClassifyInputSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        prev = question.status
        v = data.validated_data
        try:
            with transaction.atomic():
                triage.classify_question(
                    question, domain=v["domain"], skill=v["skill"],
                    difficulty=v["difficulty"], user=request.user,
                )
                audit.record_question_event(
                    event_type=audit.EVT_CLASSIFY, question=question, actor=request.user,
                    previous_state=prev, new_state=question.status,
                    extra={"domain_id": v["domain"].id, "skill_id": v["skill"].id, "difficulty": v["difficulty"]},
                )
        except TriageError as exc:
            return Response({"detail": exc.messages}, status=http_status.HTTP_400_BAD_REQUEST)
        return _question_response(question)


@extend_schema(tags=["questionbank"])
class BankQuestionApproveView(APIView):
    """POST /api/questionbank/questions/<id>/approve/ — gate to APPROVED."""

    permission_classes = QB_PERMISSIONS

    def post(self, request, pk):
        question = get_object_or_404(BankQuestion, pk=pk)
        prev = question.status
        try:
            with transaction.atomic():
                triage.approve_question(question, user=request.user)
                audit.record_question_event(
                    event_type=audit.EVT_APPROVE, question=question, actor=request.user,
                    previous_state=prev, new_state=question.status,
                )
        except TriageError as exc:
            return Response({"detail": exc.messages}, status=http_status.HTTP_400_BAD_REQUEST)
        return _question_response(question)


@extend_schema(tags=["questionbank"])
class BankQuestionRejectView(APIView):
    """POST /api/questionbank/questions/<id>/reject/."""

    permission_classes = QB_PERMISSIONS

    def post(self, request, pk):
        question = get_object_or_404(BankQuestion, pk=pk)
        data = qb.TriageRejectInputSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        prev = question.status
        with transaction.atomic():
            triage.reject_question(question, reason=data.validated_data["reason"], user=request.user)
            audit.record_question_event(
                event_type=audit.EVT_REJECT, question=question, actor=request.user,
                previous_state=prev, new_state=question.status,
                extra={"reason": data.validated_data["reason"]} if data.validated_data["reason"] else None,
            )
        return _question_response(question)


@extend_schema(tags=["questionbank"])
class BankQuestionAcceptSuggestionView(APIView):
    """POST /api/questionbank/questions/<id>/accept-suggestion/ — human applies the advisory hint."""

    permission_classes = QB_PERMISSIONS

    def post(self, request, pk):
        question = get_object_or_404(BankQuestion, pk=pk)
        prev = question.status
        try:
            with transaction.atomic():
                triage.accept_suggestion(question, user=request.user)
                audit.record_question_event(
                    event_type=audit.EVT_ACCEPT_SUGGESTION, question=question, actor=request.user,
                    previous_state=prev, new_state=question.status,
                    extra={"domain_id": question.domain_id, "skill_id": question.skill_id,
                           "difficulty": question.difficulty},
                )
        except TriageError as exc:
            return Response({"detail": exc.messages}, status=http_status.HTTP_400_BAD_REQUEST)
        return _question_response(question)


_BULK_EVENT = {
    "approve": audit.EVT_APPROVE,
    "reject": audit.EVT_REJECT,
    "classify": audit.EVT_CLASSIFY,
}


@extend_schema(tags=["questionbank"])
class BankQuestionBulkView(APIView):
    """POST /api/questionbank/questions/bulk/ — apply one action to many ids; per-id results."""

    permission_classes = QB_PERMISSIONS

    def post(self, request):
        data = qb.BulkTriageInputSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        action, ids = v["action"], v["ids"]
        results = []
        for qid in ids:
            question = BankQuestion.objects.filter(pk=qid).first()
            if question is None:
                results.append({"id": qid, "ok": False, "error": "not found"})
                continue
            prev = question.status
            try:
                with transaction.atomic():
                    if action == "approve":
                        triage.approve_question(question, user=request.user)
                        extra = None
                    elif action == "reject":
                        triage.reject_question(question, reason=v.get("reason", ""), user=request.user)
                        extra = {"reason": v["reason"]} if v.get("reason") else None
                    else:  # classify
                        triage.classify_question(
                            question, domain=v["domain"], skill=v["skill"],
                            difficulty=v["difficulty"], user=request.user,
                        )
                        extra = {"domain_id": v["domain"].id, "skill_id": v["skill"].id, "difficulty": v["difficulty"]}
                    audit.record_question_event(
                        event_type=_BULK_EVENT[action], question=question, actor=request.user,
                        previous_state=prev, new_state=question.status, extra=extra,
                    )
                results.append({"id": qid, "ok": True, "status": question.status})
            except TriageError as exc:
                results.append({"id": qid, "ok": False, "error": "; ".join(exc.messages)})
        return Response({"action": action, "results": results})


# ══════════════════════════════════════════════════════════════════════════════
# Import batch management (Phase B) — read + promote. Exact-only dedup.
# ══════════════════════════════════════════════════════════════════════════════
@extend_schema(tags=["questionbank"])
class ImportBatchListView(generics.ListAPIView):
    """GET /api/questionbank/import-batches/."""

    permission_classes = QB_PERMISSIONS
    serializer_class = qb.ImportBatchSerializer
    pagination_class = QbPagination

    def get_queryset(self):
        qs = ImportBatch.objects.all()
        if self.request.query_params.get("status"):
            qs = qs.filter(status=self.request.query_params["status"])
        return qs.order_by("-created_at", "-id")


@extend_schema(tags=["questionbank"])
class ImportBatchDetailView(generics.RetrieveAPIView):
    """GET /api/questionbank/import-batches/<id>/."""

    permission_classes = QB_PERMISSIONS
    serializer_class = qb.ImportBatchSerializer
    queryset = ImportBatch.objects.all()


@extend_schema(
    tags=["questionbank"],
    parameters=[OpenApiParameter("validation_status", str, description="VALID|WARNING|ERROR|DUPLICATE")],
)
class ImportCandidateListView(generics.ListAPIView):
    """GET /api/questionbank/import-batches/<batch_id>/candidates/."""

    permission_classes = QB_PERMISSIONS
    serializer_class = qb.ImportCandidateSerializer
    pagination_class = QbPagination

    def get_queryset(self):
        qs = ImportCandidate.objects.filter(batch_id=self.kwargs["batch_id"]).select_related(
            "duplicate_of", "promoted_question"
        )
        vs = self.request.query_params.get("validation_status")
        if vs:
            qs = qs.filter(validation_status=vs)
        return qs.order_by("order", "id")


@extend_schema(tags=["questionbank"])
class ImportCandidateDetailView(generics.RetrieveAPIView):
    """GET /api/questionbank/import-candidates/<id>/."""

    permission_classes = QB_PERMISSIONS
    serializer_class = qb.ImportCandidateSerializer
    queryset = ImportCandidate.objects.select_related("duplicate_of", "promoted_question")


@extend_schema(tags=["questionbank"])
class ImportBatchUploadView(APIView):
    """POST /api/questionbank/import-batches/upload/ — upload a PDF → parsed candidates.

    Text + best-effort page-level image extraction (PyMuPDF). Nothing is promoted
    here; candidates land in the batch for human review.
    """

    permission_classes = QB_PERMISSIONS
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        import os
        import tempfile

        from .import_pipeline import create_batch_from_pdf

        upload = request.FILES.get("file")
        if upload is None:
            return Response({"detail": "No file uploaded (field 'file')."}, status=http_status.HTTP_400_BAD_REQUEST)
        if not str(upload.name).lower().endswith(".pdf"):
            return Response({"detail": "Only PDF files are supported."}, status=http_status.HTTP_400_BAD_REQUEST)

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            for chunk in upload.chunks():
                tmp.write(chunk)
            tmp_path = tmp.name
        try:
            batch = create_batch_from_pdf(
                tmp_path,
                filename=upload.name,
                source_reference=request.data.get("source_reference", ""),
                uploaded_by=request.user if getattr(request.user, "is_authenticated", False) else None,
            )
        except RuntimeError as exc:
            return Response({"detail": str(exc)}, status=http_status.HTTP_400_BAD_REQUEST)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        return Response(qb.ImportBatchSerializer(batch).data, status=http_status.HTTP_201_CREATED)


@extend_schema(tags=["questionbank"])
class ImportBatchPromoteView(APIView):
    """POST /api/questionbank/import-batches/<id>/promote/ — VALID/WARNING → TRIAGE bank rows."""

    permission_classes = QB_PERMISSIONS

    def post(self, request, pk):
        batch = get_object_or_404(ImportBatch, pk=pk)
        raw = request.data.get("include_warnings")
        include_warnings = True if raw is None else _truthy(raw)
        with transaction.atomic():
            promoted = promote_batch(batch, include_warnings=include_warnings, user=request.user)
            audit.record_batch_event(batch=batch, actor=request.user, promoted_count=promoted)
        return Response(qb.ImportBatchSerializer(batch).data, status=http_status.HTTP_200_OK)


# ══════════════════════════════════════════════════════════════════════════════
# Student practice (M9) — APPROVED-only, self-study. Any authenticated user.
# The correct answer + explanation are NEVER in the browse/detail payloads; they
# are only returned by the answer endpoint, after the student commits an answer.
# ══════════════════════════════════════════════════════════════════════════════
PRACTICE_PERMISSIONS = [IsAuthenticatedAndNotFrozen]


def _grade_answer(correct, answer: str) -> bool:
    answer = (answer or "").strip()
    if not answer or correct is None:
        return False
    if isinstance(correct, (list, tuple)):
        return any(str(c).strip().lower() == answer.lower() for c in correct)
    return str(correct).strip().lower() == answer.lower()


@extend_schema(tags=["questionbank"])
class PracticeQuestionListView(generics.ListAPIView):
    """GET /api/questionbank/practice/ — browse APPROVED questions with filters."""

    permission_classes = PRACTICE_PERMISSIONS
    serializer_class = qb.PracticeQuestionListSerializer
    pagination_class = QbPagination

    def get_queryset(self):
        qs = BankQuestion.objects.approved().select_related("domain", "skill")
        p = self.request.query_params
        if p.get("subject"):
            qs = qs.filter(subject=p["subject"])
        if p.get("difficulty"):
            qs = qs.filter(difficulty=p["difficulty"])
        if (domain_id := _int_or_none(p.get("domain"))) is not None:
            qs = qs.filter(domain_id=domain_id)
        if (skill_id := _int_or_none(p.get("skill"))) is not None:
            qs = qs.filter(skill_id=skill_id)
        term = (p.get("search") or "").strip()
        if term:
            qs = qs.filter(Q(qb_id__icontains=term) | Q(question_text__icontains=term))
        return qs.order_by("-created_at", "-id")


@extend_schema(tags=["questionbank"])
class PracticeQuestionDetailView(generics.RetrieveAPIView):
    """GET /api/questionbank/practice/<id>/ — one APPROVED question (no answer)."""

    permission_classes = PRACTICE_PERMISSIONS
    serializer_class = qb.PracticeQuestionDetailSerializer

    def get_queryset(self):
        return BankQuestion.objects.approved().select_related("domain", "skill", "passage")


@extend_schema(tags=["questionbank"])
class PracticeAnswerView(APIView):
    """POST /api/questionbank/practice/<id>/answer/ — grade, record, reveal."""

    permission_classes = PRACTICE_PERMISSIONS

    def post(self, request, pk):
        question = get_object_or_404(BankQuestion.objects.approved(), pk=pk)
        answer = str(request.data.get("answer", "")).strip()
        is_correct = _grade_answer(question.correct_answer, answer)
        BankQuestionAttempt.objects.create(
            user=request.user, bank_question=question,
            selected_answer=answer[:255], is_correct=is_correct,
        )
        return Response({
            "is_correct": is_correct,
            "correct_answer": question.correct_answer,
            "explanation": question.explanation,
        })


@extend_schema(tags=["questionbank"], parameters=[OpenApiParameter("subject", str)])
class PracticeTaxonomyView(APIView):
    """GET /api/questionbank/practice/taxonomy/ — domains/skills with APPROVED content."""

    permission_classes = PRACTICE_PERMISSIONS

    def get(self, request):
        approved = BankQuestion.objects.approved()
        if request.query_params.get("subject"):
            approved = approved.filter(subject=request.query_params["subject"])
        domain_ids = list(approved.values_list("domain_id", flat=True).distinct())
        skill_ids = list(approved.values_list("skill_id", flat=True).distinct())
        domains = BankDomain.objects.filter(id__in=domain_ids).order_by(
            "subject", "display_order", "name"
        )
        skills = BankSkill.objects.filter(id__in=skill_ids).select_related("domain").order_by(
            "display_order", "name"
        )
        return Response({
            "domains": [{"id": d.id, "subject": d.subject, "name": d.name} for d in domains],
            "skills": [
                {"id": s.id, "domain": s.domain_id, "subject": s.domain.subject, "name": s.name}
                for s in skills
            ],
        })
