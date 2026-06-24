from __future__ import annotations

from django.db import IntegrityError, transaction
from django.db.models import Max, Avg, Count, Q as models_Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema
from drf_spectacular.types import OpenApiTypes
from django.http import HttpResponse

import secrets
from time import monotonic

from django.conf import settings as dj_settings

from access.permissions import (
    CanAuthorAssessmentContent,
    CanManageQuestions,
    CanAssignTests,
    CanViewTests,
)
from access.services import is_global_scope_staff, user_domain_subject, normalized_role
from access import constants as acc_const
from users.permissions import IsAuthenticatedAndNotFrozen

from classes.models import Assignment, Classroom, ClassroomMembership
from classes.security import classroom_authz_for_user

from .models import (
    AssessmentSet,
    AssessmentSetVersion,
    AssessmentQuestion,
    HomeworkAssignment,
    AssessmentAttempt,
    AssessmentAnswer,
    AssessmentResult,
    AssessmentAttemptAuditEvent,
    AssessmentAttemptFeedback,
)
from .throttles import (
    AssessmentAnswerPerAttemptThrottle,
    AssessmentAssignHomeworkGlobalThrottle,
    AssessmentAssignHomeworkPerClassroomThrottle,
    AssessmentAssignHomeworkThrottle,
)
from .async_tasks import grade_attempt_task
from .grading_service import grade_attempt
from .prometheus import render_assessments_prometheus_text
from .prometheus_homework import render_assessments_homework_prometheus_text
from .metrics import incr as assessments_metric_incr
from core.metrics import incr as metric_incr, incr_role as metric_incr_role
from config.error_reporting import report_error
from .worker_metrics import get_celery_worker_snapshot
from .redis_health import get_redis_health_snapshot
from .serializers import (
    AssessmentSetSerializer,
    AssessmentSetAdminSerializer,
    AssessmentSetAdminWriteSerializer,
    AssessmentSetVersionSerializer,
    AdminPublishResponseSerializer,
    AssessmentQuestionAdminWriteSerializer,
    AssignHomeworkSerializer,
    HomeworkAssignmentSerializer,
    StartAttemptSerializer,
    SaveAnswerSerializer,
    SubmitAttemptSerializer,
    AttemptSerializer,
    ResultSerializer,
    AssessmentQuestionSerializer,
    ApiAssessmentDetailSerializer,
    SaveAnswerStaleWriteSerializer,
    SaveAnswerStoredSerializer,
    AttemptBundleResponseSerializer,
    SubmitAttemptQueuedResponseSerializer,
    SubmitAttemptCompleteResponseSerializer,
    SubmitAssessmentVersionConflictSerializer,
    SubmitAttemptBadRequestSerializer,
    MyAssessmentResultResponseSerializer,
)


class AdminAssessmentSetListCreateView(APIView):
    # Default; method-specific permissions are enforced in get_permissions().
    permission_classes = [IsAuthenticatedAndNotFrozen]

    def get_permissions(self):
        if (self.request.method or "GET").upper() == "GET":
            return [p() for p in (IsAuthenticatedAndNotFrozen, CanViewTests)]
        return [p() for p in (IsAuthenticatedAndNotFrozen, CanAuthorAssessmentContent)]

    def get(self, request):
        subject = (request.query_params.get("subject") or "").strip().lower()
        category = (request.query_params.get("category") or "").strip()
        qs = AssessmentSet.objects.all().prefetch_related("questions")

        # Subject scoping:
        # - teachers: forced to their own domain subject (ignore query param)
        # - admin/test_admin/super_admin: may see all subjects; optional filter via query param
        actor = request.user
        if not is_global_scope_staff(actor) and not getattr(actor, "is_superuser", False):
            ds = user_domain_subject(actor)
            if ds in (acc_const.DOMAIN_MATH, acc_const.DOMAIN_ENGLISH):
                qs = qs.filter(subject=ds)
        else:
            if subject in (acc_const.DOMAIN_MATH, acc_const.DOMAIN_ENGLISH):
                qs = qs.filter(subject=subject)

        if category:
            qs = qs.filter(category__iexact=category)
        qs = qs.order_by("-created_at", "-id")

        paginator = LimitOffsetPagination()
        paginator.default_limit = 50
        paginator.max_limit = 200
        page = paginator.paginate_queryset(qs, request)
        if page is not None:
            return paginator.get_paginated_response(AssessmentSetSerializer(page, many=True).data)
        return Response(AssessmentSetSerializer(qs, many=True).data)

    def post(self, request):
        s = AssessmentSetAdminWriteSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        inst = s.save(created_by=request.user)
        inst = AssessmentSet.objects.filter(pk=inst.pk).prefetch_related("questions").first()
        return Response(AssessmentSetSerializer(inst).data, status=status.HTTP_201_CREATED)


class AdminGradingMetricsView(APIView):
    """
    DB-derived grading metrics (broker-agnostic):
    - "queue size" approximated by pending submitted attempts
    - latency measured from submitted_at -> result.graded_at
    """

    permission_classes = [IsAuthenticatedAndNotFrozen, CanManageQuestions]

    def get(self, request):
        now = timezone.now()
        pending = AssessmentAttempt.objects.filter(
            status=AssessmentAttempt.STATUS_SUBMITTED,
            grading_status=AssessmentAttempt.GRADING_PENDING,
        ).count()
        processing = AssessmentAttempt.objects.filter(
            status=AssessmentAttempt.STATUS_SUBMITTED,
            grading_status=AssessmentAttempt.GRADING_PROCESSING,
        ).count()
        failed = AssessmentAttempt.objects.filter(grading_status=AssessmentAttempt.GRADING_FAILED).count()

        # Rolling 24h outcomes
        since = now - timezone.timedelta(hours=24)
        completed_24h = AssessmentAttempt.objects.filter(
            grading_status=AssessmentAttempt.GRADING_COMPLETED,
            grading_last_attempt_at__gte=since,
        ).count()
        failed_24h = AssessmentAttempt.objects.filter(
            grading_status=AssessmentAttempt.GRADING_FAILED,
            grading_last_attempt_at__gte=since,
        ).count()
        retries_24h = (
            AssessmentAttempt.objects.filter(grading_last_attempt_at__gte=since)
            .aggregate(avg_attempts=Avg("grading_attempts"))
            .get("avg_attempts")
        )

        # Latency samples (last 500 results)
        res_qs = (
            AssessmentResult.objects.select_related("attempt")
            .order_by("-graded_at")
            .only("graded_at", "attempt__submitted_at")[:500]
        )
        latencies = []
        for r in res_qs:
            sub = getattr(getattr(r, "attempt", None), "submitted_at", None)
            if sub and r.graded_at:
                latencies.append((r.graded_at - sub).total_seconds())
        latencies.sort()
        def pctl(p: float) -> float | None:
            if not latencies:
                return None
            i = int(round((len(latencies) - 1) * p))
            return float(latencies[max(0, min(len(latencies) - 1, i))])

        # Trend analysis windows
        w5 = now - timezone.timedelta(minutes=5)
        w60 = now - timezone.timedelta(minutes=60)
        submitted_5m = AssessmentAttempt.objects.filter(submitted_at__gte=w5).count()
        graded_5m = AssessmentResult.objects.filter(graded_at__gte=w5).count()
        failed_5m = AssessmentAttempt.objects.filter(grading_status=AssessmentAttempt.GRADING_FAILED, grading_last_attempt_at__gte=w5).count()

        submitted_60m = AssessmentAttempt.objects.filter(submitted_at__gte=w60).count()
        graded_60m = AssessmentResult.objects.filter(graded_at__gte=w60).count()
        failed_60m = AssessmentAttempt.objects.filter(grading_status=AssessmentAttempt.GRADING_FAILED, grading_last_attempt_at__gte=w60).count()

        # Pending age distribution (proxy for queue growth/health).
        pending_rows = list(
            AssessmentAttempt.objects.filter(
                status=AssessmentAttempt.STATUS_SUBMITTED,
                grading_status=AssessmentAttempt.GRADING_PENDING,
            )
            .exclude(submitted_at__isnull=True)
            .values_list("submitted_at", flat=True)[:2000]
        )
        pending_ages = [float((now - t).total_seconds()) for t in pending_rows if t]
        pending_ages.sort()
        def pctl_age(p: float) -> float | None:
            if not pending_ages:
                return None
            i = int(round((len(pending_ages) - 1) * p))
            return float(pending_ages[max(0, min(len(pending_ages) - 1, i))])

        # Broker-aware queue size (optional, Redis only; best-effort).
        broker_url = str(getattr(dj_settings, "CELERY_BROKER_URL", "") or "").strip()
        broker_metrics = {"enabled": False, "transport": None, "queue_len": None, "detail": None}
        if broker_url.lower().startswith("redis"):
            try:
                import redis  # type: ignore

                r = redis.Redis.from_url(broker_url, socket_connect_timeout=0.5, socket_timeout=0.5)
                qname = "celery"
                qlen = int(r.llen(qname))
                broker_metrics = {"enabled": True, "transport": "redis", "queue_len": qlen, "detail": {"queue": qname}}
            except Exception as exc:
                broker_metrics = {"enabled": True, "transport": "redis", "queue_len": None, "detail": str(exc)}

        return Response(
            {
                "queue": {
                    "pending": pending,
                    "processing": processing,
                    "failed_total": failed,
                },
                "rates_24h": {
                    "completed": completed_24h,
                    "failed": failed_24h,
                    "failure_rate": round((failed_24h / (failed_24h + completed_24h)) * 100, 2)
                    if (failed_24h + completed_24h) > 0
                    else 0.0,
                    "avg_grading_attempts": float(retries_24h) if retries_24h is not None else None,
                },
                "latency_seconds": {
                    "p50": pctl(0.50),
                    "p90": pctl(0.90),
                    "p99": pctl(0.99),
                    "sample_n": len(latencies),
                },
                "trend": {
                    "submitted_per_min_5m": round(submitted_5m / 5.0, 2),
                    "graded_per_min_5m": round(graded_5m / 5.0, 2),
                    "failed_per_min_5m": round(failed_5m / 5.0, 2),
                    "submitted_per_min_60m": round(submitted_60m / 60.0, 2),
                    "graded_per_min_60m": round(graded_60m / 60.0, 2),
                    "failed_per_min_60m": round(failed_60m / 60.0, 2),
                    "pending_age_seconds": {
                        "p50": pctl_age(0.50),
                        "p90": pctl_age(0.90),
                        "p99": pctl_age(0.99),
                        "sample_n": len(pending_ages),
                    },
                },
                "broker": broker_metrics,
                "redis": get_redis_health_snapshot(),
                "workers": get_celery_worker_snapshot(),
                "backpressure": {
                    "max_inflight": int(getattr(dj_settings, "ASSESSMENT_GRADING_MAX_INFLIGHT", 500) or 500),
                    "dispatch_batch": int(getattr(dj_settings, "ASSESSMENT_GRADING_DISPATCH_BATCH", 50) or 50),
                },
                "server_time": now.isoformat(),
            }
        )


class AdminAssessmentSetDetailView(APIView):
    permission_classes = [IsAuthenticatedAndNotFrozen]

    def get_permissions(self):
        if (self.request.method or "GET").upper() == "GET":
            return [p() for p in (IsAuthenticatedAndNotFrozen, CanViewTests)]
        return [p() for p in (IsAuthenticatedAndNotFrozen, CanAuthorAssessmentContent)]

    def get(self, request, pk: int):
        inst = get_object_or_404(AssessmentSet.objects.prefetch_related("questions"), pk=pk)
        # Teacher scoping defense-in-depth (detail endpoints).
        actor = request.user
        if not is_global_scope_staff(actor) and not getattr(actor, "is_superuser", False):
            ds = user_domain_subject(actor)
            if ds and inst.subject != ds:
                return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        # Use admin serializer so the builder UI receives correct_answer + grading_config
        # (the student-facing AssessmentSetSerializer intentionally omits correct_answer).
        return Response(AssessmentSetAdminSerializer(inst).data)

    def patch(self, request, pk: int):
        inst = get_object_or_404(AssessmentSet, pk=pk)
        actor = request.user
        if not is_global_scope_staff(actor) and not getattr(actor, "is_superuser", False):
            ds = user_domain_subject(actor)
            if ds and inst.subject != ds:
                return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        s = AssessmentSetAdminWriteSerializer(inst, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        inst = s.save()
        inst = AssessmentSet.objects.filter(pk=inst.pk).prefetch_related("questions").first()
        return Response(AssessmentSetSerializer(inst).data)

    def delete(self, request, pk: int):
        inst = get_object_or_404(AssessmentSet, pk=pk)
        actor = request.user
        if not is_global_scope_staff(actor) and not getattr(actor, "is_superuser", False):
            ds = user_domain_subject(actor)
            if ds and inst.subject != ds:
                return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        inst.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminAssessmentQuestionCreateView(APIView):
    permission_classes = [IsAuthenticatedAndNotFrozen, CanAuthorAssessmentContent]

    def post(self, request, set_pk: int):
        aset = get_object_or_404(AssessmentSet, pk=set_pk)
        s = AssessmentQuestionAdminWriteSerializer(data={**request.data, "assessment_set": aset.pk})
        s.is_valid(raise_exception=True)
        # Default append order if not specified.
        if "order" not in s.validated_data:
            mx = (
                AssessmentQuestion.objects.filter(assessment_set=aset).aggregate(Max("order")).get("order__max")
                or 0
            )
            s.validated_data["order"] = int(mx) + 1
        q = s.save(assessment_set=aset)
        return Response(AssessmentQuestionAdminWriteSerializer(q).data, status=status.HTTP_201_CREATED)


class AdminAssessmentQuestionDetailView(APIView):
    permission_classes = [IsAuthenticatedAndNotFrozen, CanAuthorAssessmentContent]

    def patch(self, request, pk: int):
        q = get_object_or_404(AssessmentQuestion, pk=pk)
        s = AssessmentQuestionAdminWriteSerializer(q, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        q = s.save()
        return Response(AssessmentQuestionAdminWriteSerializer(q).data)

    def delete(self, request, pk: int):
        q = get_object_or_404(AssessmentQuestion, pk=pk)
        q.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminQuestionBankSelectView(APIView):
    """
    M4 — list APPROVED Question Bank questions for the builder's
    'Select From Question Bank' picker. Only status=APPROVED is ever returned;
    TRIAGE/IMPORTED/REJECTED/ARCHIVED questions are never selectable.
    """

    permission_classes = [IsAuthenticatedAndNotFrozen, CanAuthorAssessmentContent]

    def get(self, request):
        from .domain.bank_integration import selectable_bank_questions

        qs = selectable_bank_questions(
            subject=request.query_params.get("subject") or None,
            domain_id=request.query_params.get("domain_id") or None,
            skill_id=request.query_params.get("skill_id") or None,
            difficulty=request.query_params.get("difficulty") or None,
            search=request.query_params.get("search") or None,
        )
        paginator = LimitOffsetPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        data = [
            {
                "id": q.id,
                "qb_id": q.qb_id,
                "subject": q.subject,
                "domain": q.domain.name if q.domain_id else None,
                "skill": q.skill.name if q.skill_id else None,
                "difficulty": q.difficulty,
                "question_type": q.question_type,
                "question_text": q.question_text,
                "current_version": q.current_version.version_number if q.current_version_id else None,
            }
            for q in page
        ]
        return paginator.get_paginated_response(data)


class AdminAssessmentQuestionFromBankView(APIView):
    """M4 — create an AssessmentQuestion sourced from an APPROVED bank question."""

    permission_classes = [IsAuthenticatedAndNotFrozen, CanAuthorAssessmentContent]

    def post(self, request, set_pk: int):
        from django.core.exceptions import ValidationError as DjangoValidationError

        from questionbank.models import BankQuestion

        from .domain.bank_integration import create_question_from_bank

        aset = get_object_or_404(AssessmentSet, pk=set_pk)
        bank = get_object_or_404(BankQuestion, pk=request.data.get("bank_question_id"))
        try:
            aq = create_question_from_bank(aset, bank, order=request.data.get("order"))
        except DjangoValidationError as exc:
            msg = exc.messages[0] if getattr(exc, "messages", None) else str(exc)
            return Response({"detail": msg}, status=status.HTTP_400_BAD_REQUEST)
        return Response(AssessmentQuestionAdminWriteSerializer(aq).data, status=status.HTTP_201_CREATED)


class AdminQuestionBankTaxonomyView(APIView):
    """
    M4 — domains & skills actually used by APPROVED bank questions, for the builder
    picker's filter dropdowns.

    Lives here (not in questionbank's own API) because the questionbank taxonomy
    endpoint is gated by CanManageQuestions (global staff only) and would 403 for
    teachers — who CAN author assessments and therefore use the picker.
    """

    permission_classes = [IsAuthenticatedAndNotFrozen, CanAuthorAssessmentContent]

    def get(self, request):
        from questionbank.models import BankDomain, BankQuestion, BankSkill

        approved = BankQuestion.objects.approved()
        subject = request.query_params.get("subject") or None
        if subject:
            approved = approved.filter(subject=subject)
        domain_ids = list(approved.values_list("domain_id", flat=True).distinct())
        skill_ids = list(approved.values_list("skill_id", flat=True).distinct())
        domains = BankDomain.objects.filter(id__in=domain_ids).order_by(
            "subject", "display_order", "name"
        )
        skills = BankSkill.objects.filter(id__in=skill_ids).select_related("domain").order_by(
            "display_order", "name"
        )
        return Response(
            {
                "domains": [
                    {"id": d.id, "subject": d.subject, "name": d.name, "code": d.code}
                    for d in domains
                ],
                "skills": [
                    {
                        "id": s.id,
                        "domain": s.domain_id,
                        "subject": s.domain.subject,
                        "name": s.name,
                        "code": s.code,
                    }
                    for s in skills
                ],
            }
        )


class AssignAssessmentHomeworkView(APIView):
    """
    Teacher assigns an AssessmentSet into a classroom.
    Creates a linked `classes.Assignment` so it appears in the normal homework feed.
    """

    permission_classes = [IsAuthenticatedAndNotFrozen]
    throttle_classes = [
        AssessmentAssignHomeworkThrottle,
        AssessmentAssignHomeworkPerClassroomThrottle,
        AssessmentAssignHomeworkGlobalThrottle,
    ]

    def post(self, request):
        t0 = monotonic()
        ser = AssignHomeworkSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        from .mitigation import is_global_assignment_blocked, is_user_assignment_blocked

        if is_global_assignment_blocked():
            metric_incr("slo_homework_assign_fail_total")
            metric_incr_role("slo_homework_assign_fail_total", actor=getattr(request, "user", None))
            return Response(
                {"detail": "Assignment temporarily rate-limited system-wide. Retry shortly."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        if is_user_assignment_blocked(request.user.pk):
            metric_incr("slo_homework_assign_fail_total")
            metric_incr_role("slo_homework_assign_fail_total", actor=getattr(request, "user", None))
            return Response(
                {"detail": "Your account is temporarily blocked from assigning tests due to abuse controls."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        classroom = get_object_or_404(Classroom, pk=data["classroom_id"])
        c_authz = classroom_authz_for_user(classroom=classroom, user=request.user)
        if not c_authz.is_class_admin:
            metric_incr("slo_homework_assign_fail_total")
            metric_incr_role("slo_homework_assign_fail_total", actor=getattr(request, "user", None))
            return Response({"detail": "Only class admins can assign homework."}, status=status.HTTP_403_FORBIDDEN)

        aset = get_object_or_404(AssessmentSet.objects.prefetch_related("questions"), pk=data["set_id"])

        # Assignment permission gate (backend-enforced; never rely on frontend filtering):
        # - must have can_assign_tests in the actor context
        # - teachers must "own" the classroom (classroom.teacher == actor)
        actor = request.user
        if not CanAssignTests().has_permission(request, self):
            metric_incr("slo_homework_assign_fail_total")
            metric_incr_role("slo_homework_assign_fail_total", actor=getattr(request, "user", None))
            return Response({"detail": "You do not have permission to assign tests."}, status=status.HTTP_403_FORBIDDEN)

        role = normalized_role(actor)
        if role == acc_const.ROLE_TEACHER:
            # Classroom ownership: teacher can only assign within classes they teach.
            if not c_authz.is_teacher_owner:
                metric_incr("slo_homework_assign_fail_total")
                metric_incr_role("slo_homework_assign_fail_total", actor=getattr(request, "user", None))
                return Response({"detail": "Only the classroom teacher can assign tests in this class."}, status=status.HTTP_403_FORBIDDEN)
            # Subject scope: teachers can only assign their own subject.
            ds = user_domain_subject(actor)
            if ds and aset.subject != ds:
                metric_incr("slo_homework_assign_fail_total")
                metric_incr_role("slo_homework_assign_fail_total", actor=getattr(request, "user", None))
                return Response({"detail": "You cannot assign tests outside your subject."}, status=status.HTTP_403_FORBIDDEN)

        title = (data.get("title") or "").strip() or aset.title
        instructions = (data.get("instructions") or "").strip()
        due_at = data.get("due_at")

        # Create core homework row in existing system — UNIQUE(classroom, assessment_set) + locks.
        # Nested ``atomic()`` establishes a SAVEPOINT so an IntegrityError on duplicate insert
        # does not invalidate the outer transaction under PostgreSQL.
        with transaction.atomic():
            hw = (
                HomeworkAssignment.objects.select_for_update(of=("self",))
                .select_related("assignment")
                .filter(classroom=classroom, assessment_set=aset)
                .order_by("id")
                .first()
            )
            if hw:
                assessments_metric_incr("homework_duplicate_prevented")
            else:
                assignment = Assignment.objects.create(
                    classroom=classroom,
                    created_by=request.user,
                    title=title[:200],
                    instructions=instructions,
                    due_at=due_at,
                )
                # Resolve the latest published version to pin on this assignment.
                # NULL = set has never been published (legacy / pre-snapshot path).
                pinned_version = (
                    AssessmentSetVersion.objects.filter(assessment_set=aset)
                    .order_by("-version_number")
                    .first()
                )

                try:
                    with transaction.atomic():
                        hw = HomeworkAssignment.objects.create(
                            classroom=classroom,
                            assessment_set=aset,
                            assignment=assignment,
                            assigned_by=request.user,
                            set_version=pinned_version,
                        )
                except IntegrityError:
                    assessments_metric_incr("homework_duplicate_prevented")
                    Assignment.objects.filter(pk=assignment.pk).delete()
                    hw = (
                        HomeworkAssignment.objects.select_for_update(of=("self",))
                        .select_related("assignment")
                        .filter(classroom=classroom, assessment_set=aset)
                        .order_by("id")
                        .first()
                    )
                    if not hw:
                        report_error(
                            "assessments.homework_assign_integrity_error_no_canonical",
                            context={"actor_id": request.user.pk, "classroom_id": classroom.pk, "set_id": aset.pk},
                        )
                        raise
        from .models import AssessmentHomeworkAuditEvent, GovernanceEvent

        AssessmentHomeworkAuditEvent.objects.create(
            classroom=classroom,
            assessment_set=aset,
            homework=hw,
            actor=request.user,
            event_type=AssessmentHomeworkAuditEvent.EVENT_ASSIGNED,
            payload={"host": request.get_host(), "title": title},
        )

        # Governance event: track which version (if any) was pinned to this assignment.
        from .domain.governance_events import emit_governance_event
        emit_governance_event(
            event_type=GovernanceEvent.EVENT_ASSIGNMENT_PIN,
            actor=request.user,
            entity_type="HomeworkAssignment",
            entity_id=hw.pk,
            payload={
                "set_id": aset.pk,
                "classroom_id": classroom.pk,
                "pinned_version_id": hw.set_version_id,
                "pinned_version_number": (
                    hw.set_version.version_number if hw.set_version_id else None
                ),
                "snapshot_pinned": hw.set_version_id is not None,
            },
            correlation_id=request.META.get("HTTP_X_REQUEST_ID", ""),
        )

        from .homework_abuse import evaluate_abuse_after_assignment

        evaluate_abuse_after_assignment(
            actor_id=request.user.pk,
            classroom_id=classroom.pk,
            actor_role=normalized_role(request.user),
            actor_is_global_staff=is_global_scope_staff(request.user) or bool(getattr(request.user, "is_superuser", False)),
        )

        metric_incr("slo_homework_assign_ok_total")
        metric_incr_role("slo_homework_assign_ok_total", actor=getattr(request, "user", None))
        metric_incr("slo_homework_assign_latency_ms_sum", int((monotonic() - t0) * 1000))
        metric_incr("slo_homework_assign_latency_ms_count")
        return Response(HomeworkAssignmentSerializer(hw, context={"request": request}).data, status=status.HTTP_201_CREATED)


def _audit_attempt(attempt: AssessmentAttempt, *, actor, event_type: str, payload: dict | None = None) -> None:
    AssessmentAttemptAuditEvent.objects.create(
        attempt=attempt,
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        event_type=event_type,
        payload=payload or {},
    )


# AssessmentQuestion image fields exposed to the runner/review (relative media URLs,
# matching AssessmentQuestionSerializer's output on the live path).
_QUESTION_IMAGE_FIELDS = (
    "question_image",
    "option_a_image",
    "option_b_image",
    "option_c_image",
    "option_d_image",
)


def _img_url(field) -> str | None:
    """Relative URL for an ImageField value, or None when no file is set."""
    if not field:
        return None
    try:
        return field.url
    except ValueError:
        return None


def _image_map_for(question_ids):
    """
    Resolve image URLs for a set of AssessmentQuestion ids → {id: {field: url}}.

    Snapshots don't pin images, so the frozen delivery/review paths supplement
    them from the live question rows. This is freeze-safe: django-cleanup is
    absent, so published image files are never deleted. Text/choices/correct
    answers still come from the snapshot, preserving the freeze guarantee.
    """
    rows = AssessmentQuestion.objects.filter(id__in=list(question_ids)).only(
        "id", *_QUESTION_IMAGE_FIELDS
    )
    return {
        q.id: {f: _img_url(getattr(q, f)) for f in _QUESTION_IMAGE_FIELDS}
        for q in rows
    }


class StartAttemptView(APIView):
    permission_classes = [IsAuthenticatedAndNotFrozen]

    @extend_schema(
        tags=["assessments"],
        summary="Start or resume attempt",
        request=StartAttemptSerializer,
        responses={
            200: AttemptSerializer,
            403: ApiAssessmentDetailSerializer,
            404: ApiAssessmentDetailSerializer,
        },
    )
    @transaction.atomic
    def post(self, request):
        ser = StartAttemptSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        assignment_id = int(ser.validated_data["assignment_id"])

        hw = HomeworkAssignment.objects.select_related(
            "assignment", "classroom", "assessment_set", "set_version"
        ).filter(assignment_id=assignment_id).first()
        if not hw:
            return Response({"detail": "Assessment homework not found."}, status=status.HTTP_404_NOT_FOUND)

        classroom = hw.classroom
        if not classroom.memberships.filter(user=request.user, role=ClassroomMembership.ROLE_STUDENT).exists():
            return Response({"detail": "Only students can start this assessment."}, status=status.HTTP_403_FORBIDDEN)

        # Optional: retry mode — student retries only a specific subset of
        # questions (e.g. the ones they got wrong in a previous attempt).
        # When provided, question_order is restricted to those IDs rather than
        # the full set.  This lets the frontend implement "retry incorrect only"
        # without adding a new attempt type.
        focus_ids_raw = ser.validated_data.get("focus_question_ids") or []
        focus_ids: set[int] = {int(x) for x in focus_ids_raw if isinstance(x, (int, str)) and str(x).isdigit()}

        # Reuse in-progress attempt if exists (and no focus filter requested —
        # focus mode always creates a fresh attempt).
        att = None
        if not focus_ids:
            att = (
                AssessmentAttempt.objects.select_for_update()
                .filter(homework=hw, student=request.user, status=AssessmentAttempt.STATUS_IN_PROGRESS)
                .order_by("-started_at", "-id")
                .first()
            )
        if not att:
            # Determine question IDs and version source:
            # - If hw has a pinned set_version, build the question list from the
            #   immutable snapshot — stable content regardless of live edits.
            # - Otherwise fall back to live DB query (pre-snapshot assignment).
            if hw.set_version_id:
                from .domain.snapshot_builder import questions_from_snapshot
                raw_qs = questions_from_snapshot(hw.set_version.snapshot_json)
                qids = [q["id"] for q in sorted(raw_qs, key=lambda q: (q.get("order", 0), q["id"]))]
            else:
                qids = list(
                    AssessmentQuestion.objects.filter(
                        assessment_set=hw.assessment_set,
                        is_active=True,
                    )
                    .order_by("order", "id")
                    .values_list("id", flat=True)
                )

            # Apply focus filter: only include explicitly requested question IDs
            # (validated against the full set so students can't inject arbitrary IDs).
            if focus_ids:
                qids = [qid for qid in qids if qid in focus_ids]
                if not qids:
                    return Response(
                        {"detail": "None of the requested focus questions belong to this assignment."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            secrets.SystemRandom().shuffle(qids)
            att = AssessmentAttempt.objects.create(
                homework=hw,
                student=request.user,
                last_activity_at=timezone.now(),
                grading_status=AssessmentAttempt.GRADING_PENDING,
                question_order=qids,
                # Pin the snapshot version from the homework onto the attempt so
                # grading always uses the frozen content that was delivered.
                set_version=hw.set_version,
            )
            _audit_attempt(
                att,
                actor=request.user,
                event_type=AssessmentAttemptAuditEvent.EVENT_STARTED,
                payload={
                    "question_count": len(qids),
                    "snapshot_pinned": hw.set_version_id is not None,
                    "retry_mode": bool(focus_ids),
                },
            )
        else:
            if not att.last_activity_at:
                att.last_activity_at = timezone.now()
                att.save(update_fields=["last_activity_at"])

        att = AssessmentAttempt.objects.filter(pk=att.pk).prefetch_related("answers").first()
        return Response(AttemptSerializer(att).data, status=status.HTTP_200_OK)


class AttemptBundleView(APIView):
    """
    Student-facing attempt bootstrap: return attempt + sanitized question list
    (no correct answers), ordered by the per-attempt shuffle.
    """

    permission_classes = [IsAuthenticatedAndNotFrozen]

    @extend_schema(
        tags=["assessments"],
        summary="Attempt bundle (attempt + set + questions)",
        responses={
            200: AttemptBundleResponseSerializer,
            403: ApiAssessmentDetailSerializer,
            404: ApiAssessmentDetailSerializer,
        },
    )
    def get(self, request, attempt_id: int):
        att = AssessmentAttempt.objects.select_related(
            "homework__classroom", "homework__assessment_set", "set_version"
        ).filter(pk=attempt_id, student=request.user).first()
        if not att:
            return Response({"detail": "Attempt not found."}, status=status.HTTP_404_NOT_FOUND)

        hw = att.homework
        if not hw.classroom.memberships.filter(user=request.user, role=ClassroomMembership.ROLE_STUDENT).exists():
            return Response({"detail": "Only students can view this attempt."}, status=status.HTTP_403_FORBIDDEN)

        aset = hw.assessment_set
        order_ids = [int(x) for x in (att.question_order or []) if isinstance(x, (int, str)) and str(x).isdigit()]

        # ── Snapshot path ─────────────────────────────────────────────────────
        # When the attempt was created from a pinned snapshot, serve questions
        # directly from snapshot_json — zero live question lookups. This
        # guarantees students always see the exact content that was locked at
        # publish time, even if the live set has been edited since.
        if att.set_version_id:
            from .domain.snapshot_builder import questions_from_snapshot

            raw_qs = questions_from_snapshot(att.set_version.snapshot_json)
            # Build a sanitized list (no correct_answer, no grading_config).
            raw_by_id = {q["id"]: q for q in raw_qs}
            sanitized = [
                {
                    "id": q["id"],
                    "order": q.get("order", 0),
                    "prompt": q.get("prompt", ""),
                    "question_type": q["question_type"],
                    "choices": q.get("choices") or [],
                    "points": q.get("points", 1),
                    # correct_answer and grading_config intentionally omitted
                }
                for q in (
                    [raw_by_id[qid] for qid in order_ids if qid in raw_by_id]
                    if order_ids else sorted(raw_qs, key=lambda q: (q.get("order", 0), q["id"]))
                )
            ]
            # Snapshots don't pin images — supplement them from the live rows so
            # diagrams/figures render in the frozen runner (matches live path).
            img_map = _image_map_for(s["id"] for s in sanitized)
            for s in sanitized:
                s.update(img_map.get(s["id"], {f: None for f in _QUESTION_IMAGE_FIELDS}))
            att = AssessmentAttempt.objects.filter(pk=att.pk).prefetch_related("answers").first()
            return Response(
                {
                    "attempt": AttemptSerializer(att).data,
                    "set": AssessmentSetSerializer(aset).data,
                    "questions": sanitized,
                    "snapshot_version": att.set_version_id,
                    # Outer classes.Assignment PK — used by student UI to navigate
                    # to /assessments/result/{assignment_id} after submit.
                    "assignment_id": hw.assignment_id,
                    # Pedagogical context block: classroom name, assignment title,
                    # due date, question count. Displayed in the runner header so
                    # students always know which class this assessment is for.
                    "meta": _build_hw_meta(hw),
                }
            )

        # ── Live path (pre-snapshot attempts) ─────────────────────────────────
        # Emit fallback telemetry — primary signal for sunset monitoring.
        try:
            from .domain.governance_events import emit_fallback_path_used
            emit_fallback_path_used(
                attempt_id=att.pk,
                set_id=aset.pk,
                context="bundle",
            )
        except Exception:
            pass  # never block delivery

        base_questions = list(
            AssessmentQuestion.objects.filter(assessment_set=aset, is_active=True).order_by("order", "id")
        )
        q_by_id = {q.id: q for q in base_questions}
        questions = [q_by_id[qid] for qid in order_ids if qid in q_by_id] if order_ids else base_questions

        att = AssessmentAttempt.objects.filter(pk=att.pk).prefetch_related("answers").first()
        return Response(
            {
                "attempt": AttemptSerializer(att).data,
                "set": AssessmentSetSerializer(aset).data,
                "questions": AssessmentQuestionSerializer(questions, many=True).data,
                "assignment_id": hw.assignment_id,
                # Pedagogical context: classroom name, assignment title, due date.
                "meta": _build_hw_meta(hw),
            }
        )


class AttemptPedagogicalReviewView(APIView):
    """
    Post-submission pedagogical review for a student's assessment attempt.

    Only accessible after the attempt has been submitted or graded — the
    instructional moment where students learn from their work.

    Returns questions WITH correct_answer, explanation, and the student's
    own answer + correctness, framed for learning (not SAT benchmarking).

    Response shape:
        meta      — classroom_name, assignment_title, set_title, set_category,
                    due_at, question_count
        result    — score_points, max_points, percent, correct_count, total_questions
                    (null when grading is still pending)
        questions — ordered list of:
                    { id, order, prompt, question_prompt, question_type,
                      choices, points, correct_answer, explanation,
                      student_answer, is_correct, points_awarded }
    """

    permission_classes = [IsAuthenticatedAndNotFrozen]

    @extend_schema(
        tags=["assessments"],
        summary="Pedagogical review bundle (post-submission, with answers)",
        responses={
            200: None,  # freeform shape — no dedicated serializer yet
            403: ApiAssessmentDetailSerializer,
            404: ApiAssessmentDetailSerializer,
        },
    )
    def get(self, request, attempt_id: int):
        att = (
            AssessmentAttempt.objects.select_related(
                "homework__classroom",
                "homework__assessment_set",
                "homework__assignment",
                "set_version",
            )
            .prefetch_related("answers__question", "teacher_feedback__teacher")
            .filter(pk=attempt_id, student=request.user)
            .first()
        )
        if not att:
            return Response({"detail": "Attempt not found."}, status=status.HTTP_404_NOT_FOUND)

        # Students only — teacher/ops views go through admin endpoints.
        hw = att.homework
        if not hw.classroom.memberships.filter(
            user=request.user, role=ClassroomMembership.ROLE_STUDENT
        ).exists():
            return Response({"detail": "Only students can view this review."}, status=status.HTTP_403_FORBIDDEN)

        # Gate: review is only meaningful after submission.
        # in_progress and abandoned attempts are not reviewable here.
        if att.status not in (
            AssessmentAttempt.STATUS_SUBMITTED,
            AssessmentAttempt.STATUS_GRADED,
        ):
            return Response(
                {"detail": "Review is only available after submission."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Build answer lookup: {question_id: answer_row}
        answer_map: dict[int, AssessmentAnswer] = {a.question_id: a for a in att.answers.all()}

        order_ids = [
            int(x) for x in (att.question_order or []) if isinstance(x, (int, str)) and str(x).isdigit()
        ]

        result_obj = AssessmentResult.objects.filter(attempt=att).first()
        result_data = ResultSerializer(result_obj).data if result_obj else None

        # ── Snapshot path ─────────────────────────────────────────────────────
        # Snapshot stores choices + correct_answer but NOT explanation or
        # question_prompt (they weren't captured at publish time).  We must
        # supplement from the live DB for those two fields.
        if att.set_version_id:
            from .domain.snapshot_builder import questions_from_snapshot

            raw_qs = questions_from_snapshot(att.set_version.snapshot_json)
            raw_by_id = {q["id"]: q for q in raw_qs}

            # Bulk-fetch live supplement fields (explanation + question_prompt only)
            snap_ids = list(raw_by_id.keys())
            live_supplement = {
                q.id: q
                for q in AssessmentQuestion.objects.filter(id__in=snap_ids).only(
                    "id", "explanation", "question_prompt"
                )
            }
            # Snapshots don't pin images — supplement from live rows (freeze-safe).
            img_map = _image_map_for(snap_ids)

            ordered = (
                [raw_by_id[qid] for qid in order_ids if qid in raw_by_id]
                if order_ids
                else sorted(raw_qs, key=lambda q: (q.get("order", 0), q["id"]))
            )

            questions_out = []
            for q in ordered:
                qid = q["id"]
                live = live_supplement.get(qid)
                ans = answer_map.get(qid)
                questions_out.append(
                    {
                        "id": qid,
                        "order": q.get("order", 0),
                        "prompt": q.get("prompt", ""),
                        "question_prompt": live.question_prompt if live else "",
                        "question_type": q["question_type"],
                        "choices": q.get("choices") or [],
                        "points": q.get("points", 1),
                        "correct_answer": q.get("correct_answer"),
                        "explanation": live.explanation if live else "",
                        **img_map.get(qid, {f: None for f in _QUESTION_IMAGE_FIELDS}),
                        # Student performance fields
                        "student_answer": ans.answer if ans else None,
                        "is_correct": ans.is_correct if ans else None,
                        "points_awarded": float(ans.points_awarded) if ans and ans.points_awarded is not None else None,
                    }
                )

            fb = getattr(att, "teacher_feedback", None)
            return Response(
                {
                    "meta": _build_hw_meta(hw),
                    "result": result_data,
                    "questions": questions_out,
                    "snapshot_pinned": True,
                    "teacher_feedback": _serialize_feedback(fb),
                }
            )

        # ── Live path (pre-snapshot attempts) ─────────────────────────────────
        aset = hw.assessment_set
        base_questions = list(
            AssessmentQuestion.objects.filter(assessment_set=aset, is_active=True).order_by("order", "id")
        )
        q_by_id = {q.id: q for q in base_questions}
        ordered = [q_by_id[qid] for qid in order_ids if qid in q_by_id] if order_ids else base_questions

        questions_out = []
        for q in ordered:
            ans = answer_map.get(q.id)
            questions_out.append(
                {
                    "id": q.id,
                    "order": q.order,
                    "prompt": q.prompt,
                    "question_prompt": q.question_prompt,
                    "question_type": q.question_type,
                    "choices": q.choices if q.choices is not None else [],
                    "points": q.points,
                    "correct_answer": q.correct_answer,
                    "explanation": q.explanation,
                    **{f: _img_url(getattr(q, f)) for f in _QUESTION_IMAGE_FIELDS},
                    # Student performance fields
                    "student_answer": ans.answer if ans else None,
                    "is_correct": ans.is_correct if ans else None,
                    "points_awarded": float(ans.points_awarded) if ans and ans.points_awarded is not None else None,
                }
            )

        fb = getattr(att, "teacher_feedback", None)
        return Response(
            {
                "meta": _build_hw_meta(hw),
                "result": result_data,
                "questions": questions_out,
                "snapshot_pinned": False,
                "teacher_feedback": _serialize_feedback(fb),
            }
        )


class AttemptTeacherFeedbackView(APIView):
    """
    Instructional feedback from a teacher on a student's assessment attempt.

    GET  — returns existing feedback (or null body) for the attempt.
           Accessible by the attempt's student (post-submission) or the
           classroom teacher/admin.

    POST — upserts (creates or replaces) the feedback body.
           Only the classroom teacher or a staff admin may write.

    The record is intentionally one-per-attempt (not a thread) so teachers
    can refine their note without creating noise.  Students see the latest
    version in the pedagogical review page.
    """

    permission_classes = [IsAuthenticatedAndNotFrozen]

    # ── helpers ────────────────────────────────────────────────────────────────

    def _get_attempt_and_hw(self, attempt_id: int):
        return (
            AssessmentAttempt.objects.select_related(
                "homework__classroom",
                "homework__classroom__memberships",
                "student",
            )
            .filter(pk=attempt_id)
            .first()
        )

    def _is_teacher_or_admin(self, request, hw) -> bool:
        from classes.security import classroom_authz_for_user
        authz = classroom_authz_for_user(hw.classroom, request.user)
        return authz.is_teacher_owner or authz.is_class_admin or is_global_scope_staff(request.user)

    def _is_student_owner(self, request, att) -> bool:
        return att.student_id == request.user.pk

    # ── GET ────────────────────────────────────────────────────────────────────

    @extend_schema(tags=["assessments"], summary="Get teacher feedback for attempt")
    def get(self, request, attempt_id: int):
        att = self._get_attempt_and_hw(attempt_id)
        if not att:
            return Response({"detail": "Attempt not found."}, status=status.HTTP_404_NOT_FOUND)

        hw = att.homework
        if not (self._is_student_owner(request, att) or self._is_teacher_or_admin(request, hw)):
            return Response({"detail": "Not permitted."}, status=status.HTTP_403_FORBIDDEN)

        fb = AssessmentAttemptFeedback.objects.filter(attempt=att).first()
        return Response(
            {
                "attempt_id": att.pk,
                "feedback": {
                    "body": fb.body,
                    "updated_at": fb.updated_at.isoformat(),
                    "teacher_name": fb.teacher.get_full_name() if fb and fb.teacher else None,
                }
                if fb
                else None,
            }
        )

    # ── POST ───────────────────────────────────────────────────────────────────

    @extend_schema(tags=["assessments"], summary="Upsert teacher feedback for attempt")
    def post(self, request, attempt_id: int):
        att = self._get_attempt_and_hw(attempt_id)
        if not att:
            return Response({"detail": "Attempt not found."}, status=status.HTTP_404_NOT_FOUND)

        hw = att.homework
        if not self._is_teacher_or_admin(request, hw):
            return Response({"detail": "Only the classroom teacher can write feedback."}, status=status.HTTP_403_FORBIDDEN)

        body = (request.data.get("body") or "").strip()
        if not body:
            return Response({"detail": "Feedback body cannot be empty."}, status=status.HTTP_400_BAD_REQUEST)
        if len(body) > 2000:
            return Response({"detail": "Feedback body must be 2000 characters or fewer."}, status=status.HTTP_400_BAD_REQUEST)

        fb, _ = AssessmentAttemptFeedback.objects.update_or_create(
            attempt=att,
            defaults={"teacher": request.user, "body": body},
        )
        return Response(
            {
                "attempt_id": att.pk,
                "feedback": {
                    "body": fb.body,
                    "updated_at": fb.updated_at.isoformat(),
                    "teacher_name": request.user.get_full_name() or request.user.email,
                },
            },
            status=status.HTTP_200_OK,
        )

    # ── DELETE ─────────────────────────────────────────────────────────────────

    @extend_schema(tags=["assessments"], summary="Delete teacher feedback for attempt")
    def delete(self, request, attempt_id: int):
        att = self._get_attempt_and_hw(attempt_id)
        if not att:
            return Response({"detail": "Attempt not found."}, status=status.HTTP_404_NOT_FOUND)

        hw = att.homework
        if not self._is_teacher_or_admin(request, hw):
            return Response({"detail": "Only the classroom teacher can delete feedback."}, status=status.HTTP_403_FORBIDDEN)

        AssessmentAttemptFeedback.objects.filter(attempt=att).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class TeacherSubmissionQueueView(APIView):
    """
    Paginated list of submitted/graded attempts for all classrooms where the
    requesting user is the teacher owner or a class admin.

    Intended for the ops submission queue: teacher sees who has submitted,
    can jump to the pedagogical review, add feedback, or note missing work.

    Query params:
        classroom_id  — filter to a single classroom (optional)
        status        — "submitted" | "graded" | "all" (default: all terminal states)
        limit         — page size (default 50, max 200)
        offset        — pagination offset

    Response item shape:
        attempt_id, student_name, student_email, submitted_at, status,
        grading_status, result_percent, assignment_title, classroom_name,
        has_feedback
    """

    permission_classes = [IsAuthenticatedAndNotFrozen]

    @extend_schema(tags=["assessments"], summary="Teacher submission queue")
    def get(self, request):
        # Gather classrooms where this user is teacher or class admin
        from classes.models import ClassroomMembership

        teacher_classroom_ids = list(
            Classroom.objects.filter(
                teacher=request.user,
            ).values_list("id", flat=True)
        ) + list(
            ClassroomMembership.objects.filter(
                user=request.user,
                role=ClassroomMembership.ROLE_TEACHER,
            ).values_list("classroom_id", flat=True)
        )
        # Also allow ops/staff to see all
        if is_global_scope_staff(request.user):
            teacher_classroom_ids = None  # unrestricted

        # Filter params
        classroom_id = request.query_params.get("classroom_id")
        status_filter = request.query_params.get("status", "all")
        limit = min(int(request.query_params.get("limit", 50)), 200)
        offset = int(request.query_params.get("offset", 0))

        qs = (
            AssessmentAttempt.objects.select_related(
                "student",
                "homework__classroom",
                "homework__assignment",
                "result",
            )
            .prefetch_related("teacher_feedback")
        )

        if teacher_classroom_ids is not None:
            if not teacher_classroom_ids:
                return Response({"count": 0, "items": []})
            qs = qs.filter(homework__classroom_id__in=teacher_classroom_ids)

        if classroom_id:
            qs = qs.filter(homework__classroom_id=int(classroom_id))

        if status_filter == "submitted":
            qs = qs.filter(status=AssessmentAttempt.STATUS_SUBMITTED)
        elif status_filter == "graded":
            qs = qs.filter(status=AssessmentAttempt.STATUS_GRADED)
        else:
            qs = qs.filter(status__in=[AssessmentAttempt.STATUS_SUBMITTED, AssessmentAttempt.STATUS_GRADED])

        qs = qs.order_by("-submitted_at", "-id")
        total = qs.count()
        page = list(qs[offset : offset + limit])

        items = []
        for att in page:
            hw = att.homework
            student = att.student
            res = getattr(att, "result", None)
            fb = getattr(att, "teacher_feedback", None)
            items.append(
                {
                    "attempt_id": att.pk,
                    "student_name": student.get_full_name() or student.email,
                    "student_email": student.email,
                    "submitted_at": att.submitted_at.isoformat() if att.submitted_at else None,
                    "status": att.status,
                    "grading_status": att.grading_status,
                    "result_percent": float(res.percent) if res else None,
                    "result_correct_count": res.correct_count if res else None,
                    "result_total_questions": res.total_questions if res else None,
                    "assignment_title": hw.assignment.title if hw and hw.assignment else None,
                    "classroom_name": hw.classroom.name if hw and hw.classroom else None,
                    "classroom_id": hw.classroom_id if hw else None,
                    "assignment_id": hw.assignment_id if hw else None,
                    "has_feedback": fb is not None,
                }
            )

        return Response({"count": total, "items": items})


class SaveAnswerView(APIView):
    permission_classes = [IsAuthenticatedAndNotFrozen]
    throttle_classes = [AssessmentAnswerPerAttemptThrottle]

    @extend_schema(
        tags=["assessments"],
        summary="Save answer for one question",
        request=SaveAnswerSerializer,
        responses={
            200: SaveAnswerStoredSerializer,
            400: ApiAssessmentDetailSerializer,
            404: ApiAssessmentDetailSerializer,
            409: SaveAnswerStaleWriteSerializer,
            410: ApiAssessmentDetailSerializer,
        },
    )
    @transaction.atomic
    def post(self, request):
        ser = SaveAnswerSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        client_seq = int(data.get("client_seq") or 0)

        att = AssessmentAttempt.objects.select_for_update(of=("self",)).select_related("homework").filter(
            pk=data["attempt_id"], student=request.user
        ).first()
        if not att:
            return Response({"detail": "Attempt not found."}, status=status.HTTP_404_NOT_FOUND)
        if att.status != AssessmentAttempt.STATUS_IN_PROGRESS:
            return Response({"detail": f"Attempt is locked ({att.lock_reason()})."}, status=status.HTTP_400_BAD_REQUEST)
        # Max lifetime gate (server-side).
        max_life = int(getattr(dj_settings, "ASSESSMENT_MAX_ATTEMPT_LIFETIME_SECONDS", 6 * 60 * 60) or 0)
        if max_life > 0 and att.started_at and (timezone.now() - att.started_at).total_seconds() > max_life:
            now = timezone.now()
            att.status = AssessmentAttempt.STATUS_ABANDONED
            att.abandoned_at = now
            att.last_activity_at = now
            att.save(update_fields=["status", "abandoned_at", "last_activity_at"])
            _audit_attempt(att, actor=request.user, event_type=AssessmentAttemptAuditEvent.EVENT_TIMEOUT_ABANDONED, payload={"reason": "max_lifetime"})
            return Response({"detail": "Attempt expired."}, status=status.HTTP_410_GONE)

        q = AssessmentQuestion.objects.filter(pk=data["question_id"], assessment_set=att.homework.assessment_set).first()
        if not q:
            return Response({"detail": "Question not found for this attempt."}, status=status.HTTP_404_NOT_FOUND)

        ans = data.get("answer", None)
        now = timezone.now()
        answered_at = now

        # Ensure the question is part of the shuffled attempt order (defense-in-depth).
        order_ids = set((att.question_order or []) or [])
        if order_ids and q.id not in order_ids:
            return Response({"detail": "Question is not part of this attempt."}, status=status.HTTP_400_BAD_REQUEST)

        row, created = AssessmentAnswer.objects.select_for_update().get_or_create(
            attempt=att,
            question=q,
            defaults={
                "answer": ans,
                "answered_at": answered_at,
                "first_seen_at": now,
                "last_seen_at": now,
                "time_spent_seconds": 0,
                "client_seq": client_seq,
            },
        )
        if not created:
            # Optimistic concurrency: reject stale/out-of-order writes (multi-tab, mobile retries).
            if client_seq and int(getattr(row, "client_seq", 0) or 0) >= client_seq:
                return Response(
                    {
                        "detail": "Stale answer update rejected.",
                        "code": "stale_write",
                        "server_client_seq": int(getattr(row, "client_seq", 0) or 0),
                        "answer_id": row.pk,
                    },
                    status=status.HTTP_409_CONFLICT,
                )
            row.answer = ans
            row.answered_at = answered_at
            if row.first_seen_at is None:
                row.first_seen_at = now
            row.last_seen_at = now
            row.client_seq = max(int(getattr(row, "client_seq", 0) or 0), int(client_seq or 0))
            # Compute time from server timestamps. Cap per-question time to avoid runaway.
            cap = int((q.grading_config or {}).get("max_seconds") or 15 * 60)
            cap = max(10, min(2 * 60 * 60, cap))
            delta = int((row.last_seen_at - row.first_seen_at).total_seconds()) if row.last_seen_at and row.first_seen_at else 0
            row.time_spent_seconds = max(0, min(cap, delta))
            row.save(
                update_fields=[
                    "answer",
                    "answered_at",
                    "first_seen_at",
                    "last_seen_at",
                    "time_spent_seconds",
                    "client_seq",
                    "updated_at",
                ]
            )

        # Active time accumulation: count time between server-observed events, ignore idle gaps.
        idle_threshold = int(getattr(dj_settings, "ASSESSMENT_ACTIVE_IDLE_THRESHOLD_SECONDS", 90) or 90)
        slice_cap = int(getattr(dj_settings, "ASSESSMENT_ACTIVE_SLICE_CAP_SECONDS", 45) or 45)
        idle_threshold = max(10, min(15 * 60, idle_threshold))
        slice_cap = max(1, min(idle_threshold, slice_cap))
        prev = att.last_activity_at or att.started_at
        delta = int((now - prev).total_seconds()) if prev else 0
        add = 0
        if 0 < delta <= idle_threshold:
            add = min(slice_cap, delta)
        att.active_time_seconds = int(att.active_time_seconds or 0) + int(add)
        att.last_activity_at = now
        att.save(update_fields=["last_activity_at", "active_time_seconds"])
        _audit_attempt(
            att,
            actor=request.user,
            event_type=AssessmentAttemptAuditEvent.EVENT_ANSWER_SAVED,
            payload={"question_id": q.id, "answer_present": ans is not None},
        )
        return Response({"answer_id": row.pk}, status=status.HTTP_200_OK)


class SubmitAttemptView(APIView):
    permission_classes = [IsAuthenticatedAndNotFrozen]

    @extend_schema(
        tags=["assessments"],
        summary="Submit attempt for grading",
        request=SubmitAttemptSerializer,
        responses={
            200: SubmitAttemptCompleteResponseSerializer,
            202: SubmitAttemptQueuedResponseSerializer,
            400: SubmitAttemptBadRequestSerializer,
            404: ApiAssessmentDetailSerializer,
            409: SubmitAssessmentVersionConflictSerializer,
            410: ApiAssessmentDetailSerializer,
        },
    )
    @transaction.atomic
    def post(self, request):
        ser = SubmitAttemptSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        attempt_id = int(ser.validated_data["attempt_id"])

        att = (
            AssessmentAttempt.objects.select_for_update(of=("self",))
            .select_related("homework", "homework__assessment_set", "homework__assignment", "homework__classroom")
            .filter(pk=attempt_id, student=request.user)
            .first()
        )
        if not att:
            return Response({"detail": "Attempt not found."}, status=status.HTTP_404_NOT_FOUND)
        if att.status in (AssessmentAttempt.STATUS_SUBMITTED, AssessmentAttempt.STATUS_GRADED):
            res = AssessmentResult.objects.filter(attempt=att).first()
            return Response(
                {"attempt": AttemptSerializer(att).data, "result": ResultSerializer(res).data if res else None}
            )
        if att.status == AssessmentAttempt.STATUS_ABANDONED:
            return Response({"detail": "Attempt is abandoned."}, status=status.HTTP_400_BAD_REQUEST)
        # Max lifetime gate.
        max_life = int(getattr(dj_settings, "ASSESSMENT_MAX_ATTEMPT_LIFETIME_SECONDS", 6 * 60 * 60) or 0)
        if max_life > 0 and att.started_at and (timezone.now() - att.started_at).total_seconds() > max_life:
            return Response({"detail": "Attempt expired."}, status=status.HTTP_410_GONE)

        aset = att.homework.assessment_set
        base_questions = list(
            AssessmentQuestion.objects.filter(assessment_set=aset, is_active=True).order_by("order", "id")
        )
        q_by_id = {q.id: q for q in base_questions}
        # Validate assessment version: if question snapshot doesn't match active questions, force restart.
        active_now = set(q_by_id.keys())
        snap = set(int(x) for x in (att.question_order or []) if str(x).isdigit())
        if snap and snap != active_now:
            return Response(
                {"detail": "This assessment was updated. Please restart the attempt."},
                status=status.HTTP_409_CONFLICT,
            )

        # Use per-attempt shuffle order when present; otherwise fall back to canonical order.
        order_ids = [int(x) for x in (att.question_order or []) if isinstance(x, (int, str)) and str(x).isdigit()]
        questions = [q_by_id[qid] for qid in order_ids if qid in q_by_id] if order_ids else base_questions

        answers = {
            a.question_id: a
            for a in AssessmentAnswer.objects.filter(attempt=att, question_id__in=q_by_id.keys())
        }

        # Completeness: optionally require an answer row for every question (grading itself is deferred).
        missing = [q.id for q in questions if q.id not in answers]
        enforce = str(getattr(dj_settings, "ASSESSMENT_ENFORCE_COMPLETENESS", "False")).lower() in ("1", "true", "yes")
        if enforce and missing:
            return Response(
                {"detail": "Please answer all questions before submitting.", "missing_question_ids": missing[:50]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        total_answer_time = sum(
            int(getattr(answers.get(q.id), "time_spent_seconds", 0) or 0) for q in questions
        )

        now = timezone.now()
        prev_activity_for_slice = att.last_activity_at or att.started_at
        att.status = AssessmentAttempt.STATUS_SUBMITTED
        att.submitted_at = now
        # Harden total time: derive primarily from server attempt span, not per-answer time.
        span = int((now - att.started_at).total_seconds()) if att.started_at else 0
        span_cap = 6 * 60 * 60  # 6h safety cap
        span = max(0, min(span_cap, span))
        att.total_time_seconds = max(span, min(span_cap, total_answer_time))
        # Active time: final slice uses activity *before* we stamp submitted_at / last_activity_at.
        prev = prev_activity_for_slice
        if prev and prev < now:
            idle_threshold = int(getattr(dj_settings, "ASSESSMENT_ACTIVE_IDLE_THRESHOLD_SECONDS", 90) or 90)
            slice_cap = int(getattr(dj_settings, "ASSESSMENT_ACTIVE_SLICE_CAP_SECONDS", 45) or 45)
            idle_threshold = max(10, min(15 * 60, idle_threshold))
            slice_cap = max(1, min(idle_threshold, slice_cap))
            delta = int((now - prev).total_seconds())
            if 0 < delta <= idle_threshold:
                att.active_time_seconds = int(att.active_time_seconds or 0) + int(min(slice_cap, delta))
        att.last_activity_at = now

        # Per-question time spent (sent by the student runner). Validate to a
        # clean {str(qid): int seconds} dict so the result page can render it.
        raw_qt = request.data.get("question_times") or {}
        if isinstance(raw_qt, dict):
            cleaned_qt: dict[str, int] = {}
            for k, v in raw_qt.items():
                try:
                    qid = int(k)
                    secs = max(0, min(span_cap, int(v)))
                    cleaned_qt[str(qid)] = secs
                except (TypeError, ValueError):
                    continue
            att.question_times = cleaned_qt

        broker = str(getattr(dj_settings, "CELERY_BROKER_URL", "") or "").strip()
        eager = bool(getattr(dj_settings, "CELERY_TASK_ALWAYS_EAGER", False))
        use_async = bool(broker) or eager

        submit_update_fields = [
            "status",
            "submitted_at",
            "total_time_seconds",
            "last_activity_at",
            "active_time_seconds",
            "question_times",
        ]
        if use_async:
            att.grading_status = AssessmentAttempt.GRADING_PENDING
            att.grading_error = ""
            submit_update_fields.extend(["grading_status", "grading_error"])

        att.save(update_fields=submit_update_fields)
        _audit_attempt(att, actor=request.user, event_type=AssessmentAttemptAuditEvent.EVENT_SUBMITTED, payload={"total_time_seconds": att.total_time_seconds})

        # Sync class Submission so the grading UI shows the student as "submitted"
        try:
            from classes.homework_auto_submit import sync_assessment_submission
            sync_assessment_submission(att)
        except Exception:
            logger.exception("sync_assessment_submission failed attempt_id=%s", att.pk)

        # Always grade synchronously so students see their results immediately
        # without waiting for the teacher or a background worker. Auto-gradeable
        # question types (multiple choice, numeric, boolean, short text with
        # tolerance) score in milliseconds. If sync grading fails, we fall back
        # to the async path as a safety net.
        try:
            res = grade_attempt(attempt_id=att.pk)
            att.refresh_from_db()
            return Response({
                "attempt": AttemptSerializer(att).data,
                "result": ResultSerializer(res).data if res else None,
            })
        except Exception:
            logger.exception("sync grade_attempt failed; falling back to async attempt_id=%s", att.pk)
            if use_async:
                transaction.on_commit(lambda pk=att.pk: grade_attempt_task.delay(pk))
            att.refresh_from_db()
            return Response(
                {"attempt": AttemptSerializer(att).data, "result": None, "grading": "pending"},
                status=status.HTTP_202_ACCEPTED,
            )


class AbandonAttemptView(APIView):
    permission_classes = [IsAuthenticatedAndNotFrozen]

    @transaction.atomic
    def post(self, request):
        attempt_id = int((request.data or {}).get("attempt_id") or 0)
        if not attempt_id:
            return Response({"detail": "attempt_id is required."}, status=status.HTTP_400_BAD_REQUEST)
        att = (
            AssessmentAttempt.objects.select_for_update()
            .filter(pk=attempt_id, student=request.user)
            .first()
        )
        if not att:
            return Response({"detail": "Attempt not found."}, status=status.HTTP_404_NOT_FOUND)
        if att.status != AssessmentAttempt.STATUS_IN_PROGRESS:
            return Response({"detail": f"Attempt cannot be abandoned from {att.status}."}, status=status.HTTP_400_BAD_REQUEST)
        now = timezone.now()
        att.status = AssessmentAttempt.STATUS_ABANDONED
        att.abandoned_at = now
        att.last_activity_at = now
        att.save(update_fields=["status", "abandoned_at", "last_activity_at"])
        _audit_attempt(att, actor=request.user, event_type=AssessmentAttemptAuditEvent.EVENT_ABANDONED, payload={})
        return Response({"attempt": AttemptSerializer(att).data}, status=status.HTTP_200_OK)


class AdminAttemptStatusView(APIView):
    permission_classes = [IsAuthenticatedAndNotFrozen, CanManageQuestions]

    def get(self, request, attempt_id: int):
        att = (
            AssessmentAttempt.objects.select_related("homework", "homework__assessment_set")
            .prefetch_related("answers", "audit_events")
            .filter(pk=attempt_id)
            .first()
        )
        if not att:
            return Response({"detail": "Attempt not found."}, status=status.HTTP_404_NOT_FOUND)
        res = AssessmentResult.objects.filter(attempt=att).first()
        return Response({"attempt": AttemptSerializer(att).data, "result": ResultSerializer(res).data if res else None})


class AdminRequeueAttemptView(APIView):
    permission_classes = [IsAuthenticatedAndNotFrozen, CanManageQuestions]

    @transaction.atomic
    def post(self, request, attempt_id: int):
        att = AssessmentAttempt.objects.select_for_update().filter(pk=attempt_id).first()
        if not att:
            return Response({"detail": "Attempt not found."}, status=status.HTTP_404_NOT_FOUND)
        if att.status != AssessmentAttempt.STATUS_SUBMITTED:
            return Response({"detail": "Only submitted attempts can be requeued."}, status=status.HTTP_400_BAD_REQUEST)
        if att.grading_status != AssessmentAttempt.GRADING_FAILED:
            return Response({"detail": "Only failed attempts can be requeued."}, status=status.HTTP_400_BAD_REQUEST)
        cooldown = int(getattr(dj_settings, "ASSESSMENT_ADMIN_REQUEUE_COOLDOWN_SECONDS", 60) or 60)
        max_requeues = int(getattr(dj_settings, "ASSESSMENT_ADMIN_REQUEUE_MAX_PER_ATTEMPT", 6) or 6)
        cooldown = max(5, min(3600, cooldown))
        max_requeues = max(1, min(50, max_requeues))
        if att.grading_attempts >= max_requeues:
            return Response({"detail": "Requeue limit reached for this attempt."}, status=status.HTTP_429_TOO_MANY_REQUESTS)
        if att.grading_last_attempt_at and (timezone.now() - att.grading_last_attempt_at).total_seconds() < cooldown:
            return Response({"detail": "Requeue cooldown active."}, status=status.HTTP_429_TOO_MANY_REQUESTS)
        att.grading_status = AssessmentAttempt.GRADING_PENDING
        att.grading_error = ""
        att.save(update_fields=["grading_status", "grading_error"])
        grade_attempt_task.delay(att.pk)
        _audit_attempt(att, actor=request.user, event_type=AssessmentAttemptAuditEvent.EVENT_SUBMITTED, payload={"admin_requeue": True})
        return Response({"detail": "Requeued.", "attempt": AttemptSerializer(att).data}, status=status.HTTP_200_OK)


class AdminForceGradeAttemptView(APIView):
    permission_classes = [IsAuthenticatedAndNotFrozen, CanManageQuestions]

    def post(self, request, attempt_id: int):
        confirm = str((request.data or {}).get("confirm") or "").strip().upper()
        if confirm not in ("FORCE", "YES"):
            return Response(
                {"detail": "Confirmation required. Send { confirm: 'FORCE' } to force grading."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        res = grade_attempt(attempt_id=int(attempt_id))
        att = AssessmentAttempt.objects.filter(pk=attempt_id).first()
        if not att:
            return Response({"detail": "Attempt not found."}, status=status.HTTP_404_NOT_FOUND)
        _audit_attempt(att, actor=request.user, event_type=AssessmentAttemptAuditEvent.EVENT_GRADED, payload={"admin_force": True})
        return Response({"attempt": AttemptSerializer(att).data, "result": ResultSerializer(res).data if res else None}, status=status.HTTP_200_OK)


class AdminGradingPrometheusMetricsView(APIView):
    """
    Prometheus scrape endpoint for grading/worker gauges.
    Keep it dependency-free (mirrors realtime.prometheus pattern).
    """

    permission_classes = [IsAuthenticatedAndNotFrozen, CanManageQuestions]

    def get(self, request):
        txt = render_assessments_prometheus_text()
        return HttpResponse(txt, content_type="text/plain; version=0.0.4")


class AdminHomeworkPrometheusMetricsView(APIView):
    """
    Prometheus scrape endpoint for homework integrity counters.
    Keep it dependency-free (mirrors other prometheus endpoints).
    """

    permission_classes = [IsAuthenticatedAndNotFrozen, CanManageQuestions]

    def get(self, request):
        txt = render_assessments_homework_prometheus_text()
        return HttpResponse(txt, content_type="text/plain; version=0.0.4")


class AdminBuilderTelemetryView(APIView):
    """
    Minimal telemetry ingestion endpoint for questions-console builder recovery events.
    Best-effort counters only (Prometheus-exposed via assessments homework metrics endpoint).
    """

    permission_classes = [IsAuthenticatedAndNotFrozen, CanManageQuestions]

    def post(self, request):
        key = str((request.data or {}).get("key") or "").strip()
        allowed = {
            "invalid_selection_recovered_total",
            "stale_id_blocked_total",
            "builder_refetch_recovery_total",
        }
        if key not in allowed:
            return Response({"detail": "Invalid telemetry key."}, status=status.HTTP_400_BAD_REQUEST)
        assessments_metric_incr(key)
        return Response({"ok": True}, status=status.HTTP_200_OK)


def _serialize_feedback(fb) -> dict | None:
    """Serialize an AssessmentAttemptFeedback for student/teacher consumption."""
    if fb is None:
        return None
    return {
        "body": fb.body,
        "teacher_name": fb.teacher.get_full_name() or fb.teacher.email if fb.teacher else None,
        "updated_at": fb.updated_at.isoformat(),
    }


def _build_hw_meta(hw) -> dict:
    """
    Build the `meta` block returned to students alongside their attempt/result.

    Includes human-readable assignment context (title, set name, due date,
    question count) so the frontend can display meaningful context without
    making extra API calls.  Never includes correct_answer or grading_config.
    """
    aset = hw.assessment_set
    assignment = hw.assignment
    active_q_count = aset.questions.filter(is_active=True).count() if aset else 0
    return {
        "assignment_id": assignment.pk if assignment else None,
        "assignment_title": assignment.title if assignment else None,
        "set_title": aset.title if aset else None,
        "set_category": aset.category if aset else None,
        # Read-only exposure of the existing AssessmentSet.subject so the student
        # analytics page can group SAT strands by section. No logic/DB change.
        "set_subject": aset.subject if aset else None,
        "due_at": assignment.due_at.isoformat() if assignment and assignment.due_at else None,
        "question_count": active_q_count,
        "classroom_name": hw.classroom.name if hw.classroom else None,
    }


class MyAssessmentResultForAssignmentView(APIView):
    """
    Convenience endpoint for the homework page: given a class assignment id, return the
    student's latest attempt/result for that assessment homework.

    Response shape:
        attempt  — AssessmentAttempt data (or null if not yet started)
        result   — AssessmentResult data (or null if not yet graded)
        meta     — Human-readable context: assignment title, set name, due date, question count.
                   Always present. Frontend should use `meta` rather than `attempt.homework_id`
                   to display labels so students see real titles not internal IDs.
    """

    permission_classes = [IsAuthenticatedAndNotFrozen]

    @extend_schema(
        tags=["assessments"],
        summary="My latest attempt and result for assignment",
        responses={
            200: MyAssessmentResultResponseSerializer,
            403: ApiAssessmentDetailSerializer,
            404: ApiAssessmentDetailSerializer,
        },
    )
    def get(self, request, assignment_id: int):
        hw = HomeworkAssignment.objects.select_related(
            "assessment_set", "assignment", "classroom"
        ).filter(assignment_id=assignment_id).first()
        if not hw:
            return Response({"detail": "Assessment homework not found."}, status=status.HTTP_404_NOT_FOUND)
        membership = hw.classroom.memberships.filter(user=request.user).first()
        if not membership:
            return Response({"detail": "You are not a member of this classroom."}, status=status.HTTP_403_FORBIDDEN)
        # Admins see the assignment meta but have no student attempt
        if membership.role == ClassroomMembership.ROLE_ADMIN:
            return Response({
                "attempt": None,
                "result": None,
                "meta": _build_hw_meta(hw),
            })
        att = (
            AssessmentAttempt.objects.filter(homework=hw, student=request.user)
            .order_by("-started_at", "-id")
            .first()
        )
        if not att:
            return Response({
                "attempt": None,
                "result": None,
                "meta": _build_hw_meta(hw),
            })
        res = AssessmentResult.objects.filter(attempt=att).first()
        return Response({
            "attempt": AttemptSerializer(att).data,
            "result": ResultSerializer(res).data if res else None,
            "meta": _build_hw_meta(hw),
        })


class AdminPublishAssessmentSetView(APIView):
    """
    POST /assessments/admin/sets/{pk}/publish/

    Transition an AssessmentSet from DRAFT → PUBLISHED state by building an
    immutable AssessmentSetVersion snapshot.

    GOVERNANCE:
      - Enforces all publish preconditions (INV-001 through INV-003 from PublishService).
      - Idempotent: re-publishing identical content returns existing version (HTTP 200).
      - Creating a new version returns HTTP 201.
      - Concurrency-safe via select_for_update() inside publish_assessment_set().

    FRONTEND INTEGRATION:
      Currently the publish page calls PATCH is_active=true (legacy toggle).
      Sprint 5: swap publishSet() in builder/sets/[id]/publish/page.tsx to call this endpoint.
    """

    permission_classes = [IsAuthenticatedAndNotFrozen, CanAuthorAssessmentContent]

    @extend_schema(
        tags=["assessments"],
        summary="Publish assessment set (create immutable snapshot)",
        responses={
            200: AdminPublishResponseSerializer,
            201: AdminPublishResponseSerializer,
            400: ApiAssessmentDetailSerializer,
            404: ApiAssessmentDetailSerializer,
        },
    )
    def post(self, request, pk: int):
        from .domain.publish_service import publish_assessment_set, PublishValidationError

        # Determine whether a version already exists before publishing so we can
        # return the correct HTTP status (200 = idempotent / 201 = new version).
        existing_count = AssessmentSetVersion.objects.filter(assessment_set_id=pk).count()

        try:
            version = publish_assessment_set(set_id=pk, actor=request.user)
        except AssessmentSet.DoesNotExist:
            return Response({"detail": f"AssessmentSet #{pk} not found."}, status=status.HTTP_404_NOT_FOUND)
        except PublishValidationError as exc:
            return Response({"detail": str(exc), "code": exc.code}, status=status.HTTP_400_BAD_REQUEST)

        new_count = AssessmentSetVersion.objects.filter(assessment_set_id=pk).count()
        created = new_count > existing_count

        data = {
            "version": AssessmentSetVersionSerializer(version).data,
            "created": created,
        }
        return Response(data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class AdminValidatePublishView(APIView):
    """
    GET /assessments/admin/sets/{pk}/validate-publish/

    Dry-run publish validation — returns the full validation report without
    creating a version or changing any state.

    Used by the builder pre-publish checklist page to surface blocking and
    warning findings before the user commits to publishing.

    Response shape:
        {
            "is_publishable": bool,
            "blocking_count": int,
            "warning_count": int,
            "findings": [
                {"severity": "blocking"|"warning", "code": str, "message": str,
                 "question_id": int|null, "context": dict},
                ...
            ]
        }
    """

    permission_classes = [IsAuthenticatedAndNotFrozen, CanViewTests]

    @extend_schema(
        tags=["assessments"],
        summary="Dry-run publish validation (no state change)",
        responses={200: None, 404: ApiAssessmentDetailSerializer},
    )
    def get(self, request, pk: int):
        from .domain.publish_validator import validate_for_publish

        aset = get_object_or_404(AssessmentSet, pk=pk)
        active_questions = list(
            AssessmentQuestion.objects.filter(
                assessment_set=aset, is_active=True
            ).order_by("order", "id")
        )
        report = validate_for_publish(aset, active_questions)
        return Response(report.to_dict())


class AdminAssessmentSetVersionListView(APIView):
    """
    GET /assessments/admin/sets/{pk}/versions/

    List all published versions for an AssessmentSet, newest first.
    Used by the builder version history panel.
    """

    permission_classes = [IsAuthenticatedAndNotFrozen, CanViewTests]

    @extend_schema(
        tags=["assessments"],
        summary="List published versions for a set",
        responses={200: AssessmentSetVersionSerializer(many=True)},
    )
    def get(self, request, pk: int):
        aset = get_object_or_404(AssessmentSet, pk=pk)
        versions = AssessmentSetVersion.objects.filter(assessment_set=aset).select_related(
            "published_by"
        ).order_by("-version_number")
        return Response(AssessmentSetVersionSerializer(versions, many=True).data)


class AdminGovernanceEventListView(APIView):
    """
    GET /assessments/admin/governance-events/

    Queryable audit log for operators. Supports filtering by entity_type,
    event_type, actor_email, set_id (payload filter), and date range.
    Returns newest-first with cursor-style limit/offset pagination.

    Operators use this instead of Django admin for routine audit review.
    Never exposes payload fields that contain correct_answer data.

    Query params:
        event_type     — filter by event type (e.g. "publish", "fallback_path_used")
        entity_type    — filter by entity type (e.g. "AssessmentSetVersion")
        actor_email    — filter by actor
        since          — ISO datetime, show events after this timestamp
        until          — ISO datetime, show events before this timestamp
        limit          — default 50, max 200
        offset         — default 0
    """

    permission_classes = [IsAuthenticatedAndNotFrozen, CanViewTests]

    @extend_schema(
        tags=["assessments"],
        summary="Query governance audit log",
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        from assessments.models import GovernanceEvent

        qs = GovernanceEvent.objects.select_related("actor").order_by("-occurred_at")

        event_type = request.query_params.get("event_type", "").strip()
        entity_type = request.query_params.get("entity_type", "").strip()
        actor_email = request.query_params.get("actor_email", "").strip()
        since = request.query_params.get("since", "").strip()
        until = request.query_params.get("until", "").strip()

        if event_type:
            qs = qs.filter(event_type=event_type)
        if entity_type:
            qs = qs.filter(entity_type=entity_type)
        if actor_email:
            qs = qs.filter(actor_email__icontains=actor_email)
        if since:
            from django.utils.dateparse import parse_datetime
            dt = parse_datetime(since)
            if dt:
                qs = qs.filter(occurred_at__gte=dt)
        if until:
            from django.utils.dateparse import parse_datetime
            dt = parse_datetime(until)
            if dt:
                qs = qs.filter(occurred_at__lte=dt)

        try:
            limit = min(int(request.query_params.get("limit", 50)), 200)
            offset = max(int(request.query_params.get("offset", 0)), 0)
        except (ValueError, TypeError):
            limit, offset = 50, 0

        total = qs.count()
        page = qs[offset : offset + limit]

        results = [
            {
                "id": ev.pk,
                "event_type": ev.event_type,
                "entity_type": ev.entity_type,
                "entity_id": ev.entity_id,
                "actor_email": ev.actor_email or None,
                "occurred_at": ev.occurred_at.isoformat(),
                "correlation_id": ev.correlation_id or None,
                # Summarise payload without exposing correct_answer
                "payload_summary": _summarise_governance_payload(ev.payload),
            }
            for ev in page
        ]

        return Response({
            "count": total,
            "limit": limit,
            "offset": offset,
            "results": results,
        })


def _summarise_governance_payload(payload: dict) -> dict:
    """
    Return a safe subset of a governance event payload for the ops audit UI.
    Strips any key that looks like it could contain grading internals.
    """
    safe_keys = {
        "set_id", "set_title", "version_number", "question_count",
        "checksum", "previous_version_id", "warning_count", "blocking_count",
        "first_code", "reason", "source", "snapshot_pinned",
        "superseded_by_version_id", "superseded_by_version_number",
        "pinned_version_id", "pinned_version_number", "description",
    }
    return {k: v for k, v in (payload or {}).items() if k in safe_keys}


class AdminFailedAttemptsListView(APIView):
    """
    GET /assessments/admin/attempts/failed/

    List AssessmentAttempt rows that are in a failed/stuck state, newest first.

    An attempt is considered "stuck" if:
      - grading_status is "failed" (all automatic retries exhausted), OR
      - status is "submitted" AND submitted_at is more than 30 minutes ago
        (grading job appears to have been lost)

    Returns enough context for the operator to triage and retry without
    needing to open Django admin.

    Query params:
        limit  — default 50, max 200
        offset — default 0
    """

    permission_classes = [IsAuthenticatedAndNotFrozen, CanViewTests]

    @extend_schema(
        tags=["assessments"],
        summary="List failed/stuck scoring attempts",
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        from django.utils import timezone
        from datetime import timedelta
        from assessments.models import AssessmentAttempt

        stuck_threshold = timezone.now() - timedelta(minutes=30)

        qs = (
            AssessmentAttempt.objects.filter(
                models_Q(grading_status="failed")
                | models_Q(status="submitted", submitted_at__lt=stuck_threshold)
            )
            .select_related("student", "homework__assessment_set", "homework__assignment")
            .order_by("-submitted_at", "-id")
        )

        try:
            limit = min(int(request.query_params.get("limit", 50)), 200)
            offset = max(int(request.query_params.get("offset", 0)), 0)
        except (ValueError, TypeError):
            limit, offset = 50, 0

        total = qs.count()
        page = qs[offset : offset + limit]

        results = [
            {
                "id": att.pk,
                "student_email": att.student.email if att.student else None,
                "student_name": (
                    f"{att.student.first_name} {att.student.last_name}".strip()
                    if att.student else None
                ),
                "status": att.status,
                "grading_status": att.grading_status,
                "grading_attempts": att.grading_attempts,
                "submitted_at": att.submitted_at.isoformat() if att.submitted_at else None,
                "set_title": (
                    att.homework.assessment_set.title
                    if att.homework and att.homework.assessment_set else None
                ),
                "assignment_title": (
                    att.homework.assignment.title
                    if att.homework and att.homework.assignment else None
                ),
                "stuck_reason": (
                    "grading_failed"
                    if att.grading_status == "failed"
                    else "submitted_not_graded"
                ),
            }
            for att in page
        ]

        return Response({
            "count": total,
            "limit": limit,
            "offset": offset,
            "results": results,
        })

