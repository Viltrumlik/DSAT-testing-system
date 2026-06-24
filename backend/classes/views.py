from collections import defaultdict
import json
import logging
import mimetypes
import os
from datetime import timedelta
from statistics import mean

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import Avg, Count, Exists, OuterRef, Q
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError as DRFValidationError
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

from access import constants as acc_const
from access.models import UserAccess
from access.services import (
    actor_subject_probe_for_domain_perm,
    authorize,
    is_global_scope_staff,
    normalized_role,
)

from exams.models import PracticeTest, TestAttempt
from users.permissions import IsAuthenticatedAndNotFrozen

from .submission_validation import validate_submission_upload

from .models import (
    Classroom,
    ClassroomMembership,
    ClassPost,
    Assignment,
    AssignmentExtraAttachment,
    Submission,
    SubmissionFile,
    HomeworkStagedUpload,
    SubmissionReview,
    SubmissionAuditEvent,
    ClassroomStreamItem,
    ClassComment,
    assignment_target_practice_test_ids,
    submission_workflow_status,
)
from .submission_audit import audit_submission_event
from .stale_storage_cleanup import get_homework_storage_observability
from .db_retry import db_retry_operation
from .metrics import record_homework_submit_attempt, record_homework_submit_error, record_homework_submit_success
from .submission_limits import max_batch_upload_bytes, max_files_per_submission
from .submission_uploads import abandon_staged_uploads, stream_upload_to_storage
from .homework_auto_submit import sync_practice_submission_for_assignment
from .capabilities import can as has_cap
from .throttles import HomeworkSubmitClassThrottle, HomeworkSubmitGlobalThrottle, HomeworkSubmitThrottle
from .submission_state import (
    assert_student_edit_allowed,
    assert_teacher_grade_allowed,
    assert_teacher_return_allowed,
)
logger = logging.getLogger("security.classes")


class SubmitFlowError(Exception):
    """Nested submit phases raise this to return a DRF Response without deep returns."""

    __slots__ = ("response",)

    def __init__(self, response: Response):
        self.response = response


def _audit(sub: Submission, user, event_type: str, payload: dict | None = None) -> None:
    """Append-only audit with submission revision for traceability."""
    audit_submission_event(
        sub.pk,
        getattr(user, "pk", None),
        event_type,
        payload,
        submission_revision=sub.revision,
    )


def _revision_conflict_response(s: Submission) -> Response:
    return Response(
        {"detail": "Submission was modified. Refresh and try again.", "revision": s.revision},
        status=status.HTTP_409_CONFLICT,
    )


def _emit_grade_realtime(classroom_id: int, student_id: int) -> None:
    from realtime.services import emit_to_classroom_members, emit_to_user

    emit_to_classroom_members(
        classroom_id=classroom_id,
        event_type="stream.updated",
        payload={"classroom_id": classroom_id, "reason": "grade"},
    )
    emit_to_user(
        user_id=student_id,
        event_type="workspace.updated",
        payload={"classroom_id": classroom_id, "reason": "grade"},
    )
    emit_to_user(
        user_id=student_id,
        event_type="notifications.updated",
        payload={"reason": "graded", "classroom_id": classroom_id},
    )


def _emit_return_realtime(classroom_id: int, student_id: int) -> None:
    from realtime.services import emit_to_classroom_members, emit_to_user

    emit_to_classroom_members(
        classroom_id=classroom_id,
        event_type="stream.updated",
        payload={"classroom_id": classroom_id, "reason": "submission_returned"},
    )
    emit_to_user(
        user_id=student_id,
        event_type="workspace.updated",
        payload={"classroom_id": classroom_id, "reason": "submission_returned"},
    )


class StreamPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 50


def _actor_brief(user):
    return {
        "id": user.id,
        "email": user.email,
        "username": getattr(user, "username", None),
        "first_name": user.first_name or "",
        "last_name": user.last_name or "",
    }


def _build_stream_payload(items: list, request):
    """Hydrate stream rows with nested post / assignment / submission summaries."""
    post_ids = [i.related_id for i in items if i.stream_type == ClassroomStreamItem.TYPE_POST]
    assign_ids = [i.related_id for i in items if i.stream_type == ClassroomStreamItem.TYPE_ASSIGNMENT]
    sub_ids = [i.related_id for i in items if i.stream_type == ClassroomStreamItem.TYPE_SUBMISSION]

    posts = {p.id: p for p in ClassPost.objects.filter(pk__in=post_ids).select_related("author")}
    assigns = {a.id: a for a in Assignment.objects.filter(pk__in=assign_ids).select_related("created_by")}
    subs = {
        s.id: s
        for s in Submission.objects.filter(pk__in=sub_ids)
        .select_related("student", "assignment", "attempt", "attempt__practice_test", "review")
        .prefetch_related("files")
    }

    out = []
    for it in items:
        actor = _actor_brief(it.actor)
        row = {
            "id": it.id,
            "type": it.stream_type,
            "created_at": it.created_at,
            "actor": actor,
        }
        if it.stream_type == ClassroomStreamItem.TYPE_POST:
            p = posts.get(it.related_id)
            if not p:
                continue
            row["post"] = ClassPostSerializer(p, context={"request": request}).data
        elif it.stream_type == ClassroomStreamItem.TYPE_ASSIGNMENT:
            a = assigns.get(it.related_id)
            if not a:
                continue
            row["assignment"] = AssignmentSerializer(a, context={"request": request}).data
        else:
            s = subs.get(it.related_id)
            if not s:
                continue
            row["submission"] = SubmissionSerializer(s, context={"request": request}).data
            row["assignment_preview"] = {
                "id": s.assignment_id,
                "title": s.assignment.title,
                "due_at": s.assignment.due_at.isoformat() if s.assignment.due_at else None,
            }
        out.append(row)
    return out


class _ClassroomMemberGateMixin:
    """Fail closed with 403 when classroom exists but the user is not a member (no silent empty lists)."""

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        classroom_pk = self.kwargs.get("classroom_pk")
        if not classroom_pk:
            return
        c = Classroom.objects.filter(pk=classroom_pk).first()
        if c is None:
            return
        if not c.memberships.filter(user=request.user).exclude(
            status=ClassroomMembership.STATUS_REMOVED
        ).exists():
            raise PermissionDenied(detail="You do not have access to this classroom.")


from .serializers import (
    ClassroomSerializer,
    ClassroomCreateSerializer,
    ClassroomMembershipSerializer,
    ClassPostSerializer,
    AssignmentSerializer,
    SubmissionSerializer,
    SubmitSerializer,
    SubmissionReviewUpsertSerializer,
    SubmissionReturnSerializer,
    SubmissionAuditEventReadSerializer,
    ClassCommentSerializer,
)


class ClassroomViewSet(ModelViewSet):
    """
    - List: classes the current user is a member of
    - Create: admin only (creates admin membership for creator)
    """

    permission_classes = [IsAuthenticatedAndNotFrozen]
    queryset = Classroom.objects.all()

    def get_queryset(self):
        user = self.request.user
        # Membership is a soft delete (status=REMOVED). Gate visibility on a
        # non-removed membership, and count only non-removed members.
        active_membership = ClassroomMembership.objects.filter(
            classroom=OuterRef("pk"), user=user
        ).exclude(status=ClassroomMembership.STATUS_REMOVED)
        member_qs = (
            Classroom.objects.filter(Exists(active_membership))
            .annotate(
                members_count=Count(
                    "memberships",
                    filter=~Q(memberships__status=ClassroomMembership.STATUS_REMOVED),
                )
            )
            .distinct()
        )
        # Default visibility for classroom resources is membership-scoped. This keeps the
        # student/teacher "Classes" UX private and prevents accidental directory-wide exposure.
        #
        # Superusers and super_admin may still need a global list for operational tasks.
        # Fail-closed: `/api/classes/` is always membership-scoped for everyone.
        # A directory-wide list (ops/admin use) is exposed via a separate endpoint action.
        out = member_qs if getattr(self, "action", None) == "list" else member_qs
        return out

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return ClassroomCreateSerializer
        return ClassroomSerializer

    @action(detail=False, methods=["get"], permission_classes=[IsAuthenticatedAndNotFrozen], url_path="my-assignments")
    def my_assignments(self, request):
        """
        Returns ALL assignments across ALL classrooms the current user is enrolled in,
        with ``workflow_status`` and ``assessment_homework`` hydrated.

        This replaces the previous N+1 per-classroom fetch pattern on the student
        assessment workspace and dashboard. One request → full assignment surface.

        Response: { count, items: [ { ...assignment, classroom_id, classroom_name,
                                      workflow_status, assessment_homework } ] }
        """
        user = request.user
        enrolled = list(
            Classroom.objects.filter(
                memberships__user=user,
                memberships__status__in=ClassroomMembership.NON_REMOVED_STATUSES,
            )
            .only("id", "name", "subject")
            .distinct()
        )
        if not enrolled:
            return Response({"count": 0, "items": []})

        classroom_ids = [c.id for c in enrolled]
        classroom_map = {c.id: c for c in enrolled}

        # Single query: all assignments across enrolled classrooms.
        assignments = list(
            Assignment.objects.filter(classroom_id__in=classroom_ids)
            .select_related(
                "classroom",
                "created_by",
                "assessment_homework__assessment_set",
            )
            .annotate(_given_at=Coalesce("published_at", "created_at"))
            .order_by("classroom_id", "-_given_at", "-id")
        )

        # Build submission map for this student (one query).
        subs_map = {
            s.assignment_id: s
            for s in Submission.objects.filter(
                student=user,
                assignment__classroom_id__in=classroom_ids,
            ).select_related("review")
        }

        # Build assessment attempt map (one query via HomeworkAssignment → AssessmentAttempt).
        assessment_wf_map: dict[int, str] = {}  # assignment_id → workflow_status string
        # attempt_id for in-progress assessment attempts (enables one-click resume)
        assessment_attempt_id_map: dict[int, int] = {}  # assignment_id → attempt_id
        try:
            from assessments.models import HomeworkAssignment as AssessHW, AssessmentAttempt, AssessmentResult

            hw_rows = list(
                AssessHW.objects.filter(classroom_id__in=classroom_ids).select_related("assignment")
            )
            if hw_rows:
                hw_by_assignment = {h.assignment_id: h for h in hw_rows}
                latest_by_hw: dict[int, AssessmentAttempt] = {}
                for att in AssessmentAttempt.objects.filter(
                    student=user,
                    homework_id__in=[h.id for h in hw_rows],
                ).order_by("-started_at", "-id"):
                    if att.homework_id not in latest_by_hw:
                        latest_by_hw[att.homework_id] = att

                res_by_attempt = {
                    r.attempt_id: r
                    for r in AssessmentResult.objects.filter(
                        attempt_id__in=[a.id for a in latest_by_hw.values()]
                    )
                }

                for assign_id, h in hw_by_assignment.items():
                    att = latest_by_hw.get(h.id)
                    res = res_by_attempt.get(att.id) if att else None
                    if att is None:
                        assessment_wf_map[assign_id] = "not_started"
                    elif res is not None:
                        assessment_wf_map[assign_id] = "graded"
                    elif att.status == "submitted":
                        assessment_wf_map[assign_id] = "submitted"
                    elif att.status == "in_progress":
                        assessment_wf_map[assign_id] = "in_progress"
                        # Surface the attempt ID so the frontend can deep-link
                        # directly to the runner, skipping the start-page interstitial.
                        assessment_attempt_id_map[assign_id] = att.id
                    else:
                        assessment_wf_map[assign_id] = att.status or "not_started"
        except Exception:
            logger.exception("my_assignments: assessment hydration failed user_id=%s", user.pk)

        items = []
        for a in assignments:
            hw = getattr(a, "assessment_homework", None)
            hw_set = getattr(hw, "assessment_set", None) if hw else None

            # Determine workflow_status: assessment path takes precedence.
            if hw is not None:
                wf = assessment_wf_map.get(a.id, "not_started")
            else:
                wf = submission_workflow_status(subs_map.get(a.id))

            assessment_homework_payload = None
            if hw is not None:
                assessment_homework_payload = {
                    "homework_id": hw.id,
                    "set": (
                        {
                            "id": hw_set.id,
                            "subject": hw_set.subject,
                            "category": hw_set.category,
                            "title": hw_set.title,
                            "description": getattr(hw_set, "description", ""),
                        }
                        if hw_set
                        else None
                    ),
                }

            classroom = classroom_map.get(a.classroom_id)
            items.append({
                "id": a.id,
                "title": a.title,
                "due_at": a.due_at.isoformat() if a.due_at else None,
                "created_at": a.created_at.isoformat(),
                "classroom_id": a.classroom_id,
                "classroom_name": classroom.name if classroom else f"Class #{a.classroom_id}",
                "classroom_subject": classroom.subject if classroom else None,
                "workflow_status": wf,
                "assessment_homework": assessment_homework_payload,
                # attempt_id is present only when workflow_status == "in_progress".
                # Enables the frontend to deep-link directly to the runner
                # (/assessments/attempt/{attempt_id}), bypassing the start-page
                # interstitial for one-click resume UX.
                "attempt_id": assessment_attempt_id_map.get(a.id),
                "has_practice_content": bool(
                    assignment_target_practice_test_ids(a) or hw is not None
                ),
            })

        return Response({"count": len(items), "items": items})

    @action(detail=False, methods=["get"], permission_classes=[IsAuthenticatedAndNotFrozen], url_path="my-schedule")
    def my_schedule(self, request):
        """
        Student lessons calendar for ?from=YYYY-MM-DD&to=YYYY-MM-DD (range capped at 70 days):
          - recurring class meetings from each enrolled active classroom's lesson_days
            (ODD → Mon/Wed/Fri, EVEN → Tue/Thu/Sat) + lesson_time + subject, from start_date,
          - assigned mock/midterm tests on their practice_date,
          - published assignment due dates.
        Returns a flat ``events`` list the frontend buckets by day.
        """
        import datetime as _dt
        from exams.models import MockExam

        user = request.user

        def _parse(s):
            try:
                return _dt.date.fromisoformat(str(s))
            except (TypeError, ValueError):
                return None

        today = timezone.localdate()
        frm = _parse(request.query_params.get("from")) or today.replace(day=1)
        to = _parse(request.query_params.get("to")) or (frm + _dt.timedelta(days=41))
        if to < frm:
            frm, to = to, frm
        if (to - frm).days > 70:
            to = frm + _dt.timedelta(days=70)

        # ODD = Mon/Wed/Fri, EVEN = Tue/Thu/Sat (Python weekday: Mon=0 … Sun=6).
        # Mirrors frontend src/lib/classroomSchedule.ts.
        ODD_WD = {0, 2, 4}
        EVEN_WD = {1, 3, 5}
        SUBJECT_LABEL = {"MATH": "Math", "ENGLISH": "English"}

        events: list[dict] = []

        classes = list(
            Classroom.objects.filter(
                memberships__user=user,
                memberships__status__in=ClassroomMembership.NON_REMOVED_STATUSES,
                is_active=True,
            )
            .only("id", "name", "subject", "lesson_days", "lesson_time", "start_date")
            .distinct()
        )
        for c in classes:
            if c.lesson_days == Classroom.DAYS_ODD:
                wd = ODD_WD
            elif c.lesson_days == Classroom.DAYS_EVEN:
                wd = EVEN_WD
            else:
                continue
            start = c.start_date or frm
            subj = SUBJECT_LABEL.get(str(c.subject).upper(), str(c.subject or ""))
            d = frm
            while d <= to:
                if d.weekday() in wd and d >= start:
                    events.append({
                        "date": d.isoformat(),
                        "type": "class",
                        "title": c.name,
                        "sub": subj,
                        "time": c.lesson_time or "",
                        "classroom_id": c.id,
                    })
                d += _dt.timedelta(days=1)

        for m in (
            MockExam.objects.filter(assigned_users=user, practice_date__range=(frm, to))
            .only("id", "title", "kind", "practice_date")
            .distinct()
        ):
            is_mt = m.kind == MockExam.KIND_MIDTERM
            events.append({
                "date": m.practice_date.isoformat(),
                "type": "midterm" if is_mt else "mock",
                "title": m.title or ("Midterm" if is_mt else "Mock exam"),
                "sub": "Midterm · test-day conditions" if is_mt else "Full-length · test-day conditions",
                "time": "",
                "mock_exam_id": m.id,
            })

        class_ids = [c.id for c in classes]
        if class_ids:
            for a in (
                Assignment.objects.filter(
                    classroom_id__in=class_ids,
                    status=Assignment.STATUS_PUBLISHED,
                    due_at__date__range=(frm, to),
                )
                .select_related("classroom")
            ):
                dd = timezone.localtime(a.due_at).date()
                events.append({
                    "date": dd.isoformat(),
                    "type": "assignment",
                    "title": a.title,
                    "sub": f"Due · {a.classroom.name}",
                    "time": "",
                    "classroom_id": a.classroom_id,
                    "assignment_id": a.id,
                })

        return Response({"from": frm.isoformat(), "to": to.isoformat(), "events": events})

    @action(detail=False, methods=["get"], url_path="directory")
    def directory(self, request):
        """Directory-wide classroom list (governance: admin / super_admin / superuser)."""
        user = request.user
        if not (getattr(user, "is_superuser", False) or normalized_role(user) in (acc_const.ROLE_SUPER_ADMIN, acc_const.ROLE_ADMIN)):
            raise PermissionDenied(detail="You do not have permission to view the classroom directory.")
        qs = Classroom.objects.annotate(members_count=Count("memberships")).distinct().order_by("-created_at")
        page = self.paginate_queryset(qs)
        if page is not None:
            ser = ClassroomSerializer(page, many=True, context={"request": request})
            return self.get_paginated_response(ser.data)
        return Response(ClassroomSerializer(qs, many=True, context={"request": request}).data)

    def get_object(self):
        queryset = self.filter_queryset(self.get_queryset())
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        lookup = self.kwargs.get(lookup_url_kwarg)
        try:
            return queryset.get(**{self.lookup_field: lookup})
        except Classroom.DoesNotExist:
            if Classroom.objects.filter(pk=lookup).exists():
                raise PermissionDenied(detail="You do not have access to this classroom.")
            raise NotFound()

    def create(self, request, *args, **kwargs):
        # Permission + subject-domain enforced via authorize(...).
        subj = (request.data or {}).get("subject")
        platform_subject = (
            acc_const.SUBJECT_MATH_PLATFORM
            if subj == Classroom.SUBJECT_MATH
            else acc_const.SUBJECT_ENGLISH_PLATFORM
            if subj == Classroom.SUBJECT_ENGLISH
            else None
        )
        if not authorize(request.user, acc_const.PERM_CREATE_CLASSROOM, subject=platform_subject):
            return Response(
                {"detail": "You do not have permission to create groups."},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        teacher = serializer.validated_data.get("teacher") or request.user
        classroom = serializer.save(created_by=request.user, teacher=teacher)
        ClassroomMembership.objects.get_or_create(
            classroom=classroom, user=request.user, defaults={"role": "ADMIN"}
        )
        ClassroomMembership.objects.get_or_create(
            classroom=classroom, user=teacher, defaults={"role": "ADMIN"}
        )
        dom = (
            acc_const.DOMAIN_MATH
            if classroom.subject == Classroom.SUBJECT_MATH
            else acc_const.DOMAIN_ENGLISH
        )
        UserAccess.objects.get_or_create(
            user=request.user,
            subject=dom,
            classroom=classroom,
            defaults={"granted_by": request.user},
        )
        logger.info(
            "classroom_created id=%s subject=%s created_by_id=%s teacher_id=%s",
            classroom.pk,
            classroom.subject,
            request.user.pk,
            getattr(teacher, "pk", None),
        )
        out = ClassroomSerializer(classroom, context={"request": request}).data
        return Response(out, status=status.HTTP_201_CREATED)

    def _ensure_class_admin(self, classroom):
        if not has_cap(self.request.user, classroom, "can_manage_class"):
            return Response({"detail": "Only class teachers can edit groups."}, status=status.HTTP_403_FORBIDDEN)
        return None

    def _sync_teacher_membership(self, instance):
        teacher = instance.teacher
        if teacher:
            ClassroomMembership.objects.get_or_create(
                classroom=instance, user=teacher, defaults={"role": "ADMIN"}
            )

    # PATCH calls partial_update → UpdateModelMixin.update(partial=True). Override update only
    # (do not delegate update → partial_update or recursion occurs).
    def update(self, request, *args, **kwargs):
        classroom = self.get_object()
        denied = self._ensure_class_admin(classroom)
        if denied is not None:
            return denied
        response = super().update(request, *args, **kwargs)
        self._sync_teacher_membership(self.get_object())
        return response

    def destroy(self, request, *args, **kwargs):
        classroom = self.get_object()
        if not has_cap(request.user, classroom, "can_delete_class"):
            return Response({"detail": "Only the class owner can delete this class."}, status=status.HTTP_403_FORBIDDEN)
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticatedAndNotFrozen])
    def regenerate_code(self, request, pk=None):
        classroom = self.get_object()
        if not has_cap(request.user, classroom, "can_manage_class"):
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)
        classroom.join_code = ""
        classroom.save(update_fields=["join_code", "updated_at"])
        return Response({"join_code": classroom.join_code})

    @action(detail=True, methods=["get"], permission_classes=[IsAuthenticatedAndNotFrozen])
    def people(self, request, pk=None):
        classroom = self.get_object()
        memberships = (
            classroom.memberships.select_related("user")
            .exclude(status=ClassroomMembership.STATUS_REMOVED)
            .order_by("role", "-joined_at")
        )
        return Response(ClassroomMembershipSerializer(memberships, many=True, context={"request": request}).data)

    @action(
        detail=True,
        methods=["get"],
        permission_classes=[IsAuthenticatedAndNotFrozen],
        url_path="homework-storage-metrics",
    )
    def homework_storage_metrics(self, request, pk=None):
        """Stale homework blob cleanup backlog and retry stats (platform-wide; class admins only)."""
        classroom = self.get_object()
        if not has_cap(request.user, classroom, "can_manage_class"):
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)
        return Response(get_homework_storage_observability())

    @action(detail=True, methods=["get"], permission_classes=[IsAuthenticatedAndNotFrozen], url_path="assignment-options")
    def assignment_options(self, request, pk=None):
        """
        Pastpaper practice tests the teacher may attach to homework.
        Uses the same visibility rules as /exams/ for the practice library.
        """
        classroom = self.get_object()
        if not has_cap(request.user, classroom, "can_manage_assignments"):
            return Response(
                {"detail": "Only class teachers can load assignment options."},
                status=status.HTTP_403_FORBIDDEN,
            )

        from exams.views import PracticeTestViewSet

        pvs = PracticeTestViewSet()
        pvs.request = request
        pvs.format_kwarg = None
        pt_qs = pvs.get_queryset()

        practice_tests = []
        for pt in pt_qs:
            practice_tests.append(
                {
                    "id": pt.id,
                    "title": (pt.title or "").strip(),
                    "subject": pt.subject,
                    "label": pt.label or "",
                    "form_type": pt.form_type,
                    "practice_date": pt.practice_date.isoformat() if pt.practice_date else None,
                    "created_at": pt.created_at.isoformat() if pt.created_at else None,
                    "mock_exam": None,
                    "collection_name": pt.collection_name or "",
                    "is_published": pt.is_published,
                }
            )

        # Assessment sets
        from assessments.models import AssessmentSet
        assessment_sets = []
        for aset in AssessmentSet.objects.filter(is_active=True).order_by("-created_at"):
            assessment_sets.append({
                "id": aset.id,
                "title": aset.title,
                "subject": aset.subject,
                "category": aset.category or "",
                "description": aset.description or "",
                "question_count": aset.questions.filter(is_active=True).count(),
            })

        # Practice test packs (custom user-created)
        from exams.models import PracticeTestPack
        practice_test_packs = []
        for ptp in PracticeTestPack.objects.filter(is_published=True).order_by("-created_at"):
            practice_test_packs.append({
                "id": ptp.id,
                "title": ptp.title or "",
                "description": ptp.description or "",
                "section_count": ptp.sections.count(),
            })

        # Interactive midterms (MockExam kind=MIDTERM) the teacher may assign to this class.
        from exams.models import MockExam
        midterms = []
        for mid in MockExam.objects.filter(
            kind=MockExam.KIND_MIDTERM, is_published=True
        ).order_by("-id"):
            midterms.append({
                "id": mid.id,
                "title": mid.title or "",
                "subject": mid.midterm_subject,
                "scoring_scale": mid.midterm_scoring_scale,
                "module_count": mid.midterm_module_count,
            })

        return Response({
            "practice_tests": practice_tests,
            "assessment_sets": assessment_sets,
            "practice_test_packs": practice_test_packs,
            "midterms": midterms,
        })

    @action(detail=True, methods=["get"], permission_classes=[IsAuthenticatedAndNotFrozen], url_path="leaderboard")
    def leaderboard(self, request, pk=None):
        """
        Pastpaper / practice-test homework stats: per-assignment group mean, per-student ranks,
        and score on the most recently assigned practice test in this class.
        """
        classroom = self.get_object()
        if not classroom.memberships.filter(user=request.user).exclude(
            status=ClassroomMembership.STATUS_REMOVED
        ).exists():
            return Response({"detail": "Not a member."}, status=status.HTTP_403_FORBIDDEN)

        student_memberships = list(
            classroom.memberships.filter(role=ClassroomMembership.ROLE_STUDENT)
            .select_related("user")
            .order_by("user__first_name", "user__last_name", "user__email")
        )
        student_ids = [m.user_id for m in student_memberships]
        n_students = len(student_ids)

        practice_assignments = list(
            Assignment.objects.filter(classroom=classroom)
            .filter(
                Q(practice_test__isnull=False)
                | Q(practice_test_ids__isnull=False)
                | Q(mock_exam__isnull=False)
            )
            .select_related("practice_test", "mock_exam")
            .order_by("-created_at")
        )
        assign_ids = [a.id for a in practice_assignments]
        latest_pa = practice_assignments[0] if practice_assignments else None

        scores_by_assignment: dict[int, list[int]] = defaultdict(list)
        sub_map: dict[tuple[int, int], Submission] = {}
        if assign_ids and student_ids:
            subs_qs = Submission.objects.filter(
                assignment_id__in=assign_ids,
                student_id__in=student_ids,
            ).select_related("attempt", "assignment", "assignment__practice_test")
            for s in subs_qs:
                sub_map[(s.student_id, s.assignment_id)] = s
                att = s.attempt
                if att and att.is_completed and att.score is not None:
                    targets = assignment_target_practice_test_ids(s.assignment)
                    if att.practice_test_id in targets:
                        scores_by_assignment[s.assignment_id].append(att.score)

        assignments_summary = []
        for a in practice_assignments:
            scores = scores_by_assignment.get(a.id, [])
            target_ids = assignment_target_practice_test_ids(a)
            pt_first = PracticeTest.objects.filter(pk=target_ids[0]).first() if target_ids else None
            title_fallback = (pt_first.collection_name or None) if pt_first else None
            assignments_summary.append(
                {
                    "assignment_id": a.id,
                    "title": a.title,
                    "due_at": a.due_at.isoformat() if a.due_at else None,
                    "created_at": a.created_at.isoformat() if a.created_at else None,
                    "practice_test_id": target_ids[0] if target_ids else None,
                    "practice_test_title": (pt_first.title if pt_first else None) or title_fallback,
                    "subject": pt_first.subject if pt_first else None,
                    "group_mean_score": round(mean(scores), 1) if scores else None,
                    "completed_count": len(scores),
                    "student_headcount": n_students,
                    "completion_rate_pct": round(100.0 * len(scores) / n_students, 1) if n_students else 0.0,
                }
            )

        # Teacher homework grades: mean of SubmissionReview.grade (non-null) + count of all reviewed submissions.
        review_stats = (
            Submission.objects.filter(
                assignment__classroom=classroom,
                student_id__in=student_ids,
                status=Submission.STATUS_REVIEWED,
            )
            .exclude(review__grade__isnull=True)
            .values("student_id")
            .annotate(avg_grade=Avg("review__grade"))
        )
        review_avg_by_student: dict[int, float | None] = {
            r["student_id"]: float(r["avg_grade"]) if r["avg_grade"] is not None else None for r in review_stats
        }
        reviewed_count_by_student = {
            r["student_id"]: r["n"]
            for r in Submission.objects.filter(
                assignment__classroom=classroom,
                student_id__in=student_ids,
                status=Submission.STATUS_REVIEWED,
            )
            .values("student_id")
            .annotate(n=Count("id"))
        }
        max_review_cnt = max(reviewed_count_by_student.values(), default=0)
        min_cfg = int(getattr(settings, "CLASSROOM_LEADERBOARD_MIN_REVIEWED_FOR_RANK", 2))
        effective_min_for_rank = min(min_cfg, max_review_cnt) if max_review_cnt else min_cfg

        homework_assignment_count = Assignment.objects.filter(classroom=classroom).count()
        turn_in_rows = (
            Submission.objects.filter(assignment__classroom=classroom, student_id__in=student_ids)
            .exclude(status=Submission.STATUS_DRAFT)
            .values("student_id")
            .annotate(n=Count("id"))
        )
        turn_in_by_student = {row["student_id"]: row["n"] for row in turn_in_rows}

        homework_grade_rows: list[dict] = []
        for mem in student_memberships:
            uid = mem.user_id
            avg_g = review_avg_by_student.get(uid)
            cnt = reviewed_count_by_student.get(uid, 0)
            turn_in = turn_in_by_student.get(uid, 0)
            completion_pct = (
                round(100.0 * turn_in / homework_assignment_count, 1) if homework_assignment_count else None
            )
            homework_grade_rows.append(
                {
                    "user_id": uid,
                    "first_name": mem.user.first_name or "",
                    "last_name": mem.user.last_name or "",
                    "email": mem.user.email or "",
                    "average_review_grade": round(avg_g, 2) if avg_g is not None else None,
                    "graded_submission_count": cnt,
                    "classwork_turn_in_count": turn_in,
                    "homework_completion_rate_pct": completion_pct,
                }
            )
        homework_grade_rows.sort(
            key=lambda r: (
                -(r["average_review_grade"] if r["average_review_grade"] is not None else -1.0),
                -r["graded_submission_count"],
                -(r["homework_completion_rate_pct"] or 0),
                -r["classwork_turn_in_count"],
                (r["first_name"] or r["email"]).lower(),
            )
        )
        for i, r in enumerate(homework_grade_rows, start=1):
            r["rank_ordinal"] = i
            confident = (
                r["graded_submission_count"] >= effective_min_for_rank and r["average_review_grade"] is not None
            )
            r["rank_confidence"] = "high" if confident else "low"
            r["rank"] = i if confident else None
        review_avgs = [r["average_review_grade"] for r in homework_grade_rows if r["average_review_grade"] is not None]
        class_average_review_grade = round(mean(review_avgs), 2) if review_avgs else None

        rows = []
        for mem in student_memberships:
            u = mem.user
            scores_list: list[int] = []
            for a in practice_assignments:
                s = sub_map.get((u.id, a.id))
                att = s.attempt if s else None
                if att and att.is_completed and att.score is not None:
                    if att.practice_test_id in assignment_target_practice_test_ids(a):
                        scores_list.append(att.score)

            latest_practice = None
            if latest_pa:
                s = sub_map.get((u.id, latest_pa.id))
                att = s.attempt if s else None
                lt_ids = assignment_target_practice_test_ids(latest_pa)
                pt = PracticeTest.objects.filter(pk=lt_ids[0]).first() if lt_ids else None
                title_fb = (pt.collection_name or None) if pt else None
                latest_practice = {
                    "assignment_id": latest_pa.id,
                    "assignment_title": latest_pa.title,
                    "practice_test_title": (pt.title if pt else None) or title_fb,
                    "subject": pt.subject if pt else None,
                    "score": att.score
                    if att and att.is_completed and att.score is not None
                    else None,
                    "submitted_at": att.submitted_at.isoformat() if att and att.submitted_at else None,
                    "attempt_id": att.id if att else None,
                    "in_progress": bool(att and not att.is_completed),
                }

            practice_average = round(sum(scores_list) / len(scores_list), 1) if scores_list else None
            ravg = review_avg_by_student.get(u.id)
            rcnt = reviewed_count_by_student.get(u.id, 0)
            rows.append(
                {
                    "user_id": u.id,
                    "first_name": u.first_name or "",
                    "last_name": u.last_name or "",
                    "username": getattr(u, "username", None) or "",
                    "email": u.email or "",
                    "latest_practice": latest_practice,
                    "practice_average": practice_average,
                    "practice_completed_count": len(scores_list),
                    "practice_total_assigned": len(practice_assignments),
                    "average_review_grade": round(ravg, 2) if ravg is not None else None,
                    "review_graded_count": rcnt,
                }
            )

        rows.sort(
            key=lambda r: (
                -(r["practice_average"] if r["practice_average"] is not None else -1.0),
                -r["practice_completed_count"],
                (r["first_name"] or r["email"]).lower(),
            )
        )
        for i, r in enumerate(rows, start=1):
            r["rank"] = i

        student_avgs = [r["practice_average"] for r in rows if r["practice_average"] is not None]
        class_practice_average = round(mean(student_avgs), 1) if student_avgs else None

        global_means = [x["group_mean_score"] for x in assignments_summary if x["group_mean_score"] is not None]
        overall_assignment_mean = round(mean(global_means), 1) if global_means else None

        return Response(
            {
                "classroom_id": classroom.id,
                "classroom_name": classroom.name,
                "student_count": n_students,
                "practice_assignment_count": len(practice_assignments),
                "class_practice_average": class_practice_average,
                "overall_group_mean_of_assignments": overall_assignment_mean,
                "assignments_summary": assignments_summary,
                "students": rows,
                "homework_grade_leaderboard": {
                    "description": (
                        "Rankings by average teacher grade (SubmissionReview.grade) across "
                        "submissions marked reviewed in this class. Ties use graded count, then "
                        "classwork completion rate, then number of non-draft turn-ins."
                    ),
                    "class_average_review_grade": class_average_review_grade,
                    "classwork_assignment_count": homework_assignment_count,
                    "effective_min_reviewed_for_rank": effective_min_for_rank,
                    "ranking_note": (
                        f"Rank is shown only when a student has at least {effective_min_for_rank} "
                        "graded homework item(s) in this class and a numeric average; "
                        "otherwise rank is null (rank_ordinal still reflects sort order). "
                        "Completion rate is non-draft submissions ÷ total class assignments."
                    ),
                    "rows": homework_grade_rows,
                },
            }
        )

    @action(detail=True, methods=["get"], permission_classes=[IsAuthenticatedAndNotFrozen], url_path="interventions")
    def interventions(self, request, pk=None):
        """
        Teacher/admin intervention signals for a classroom.

        Returns actionable signals the teacher can act on immediately:
          - overdue_students:   students with ≥1 overdue assignment not submitted
          - inactive_students:  students with no submission activity in 7 days
          - low_score_students: students whose average assessment score is below 60%
          - completion_summary: per-assignment completion rates
          - class_stats:        overall health metrics

        Access: teachers and admins of the classroom only.
        """
        classroom = self.get_object()
        user = request.user
        membership = classroom.memberships.filter(user=user).exclude(
            status=ClassroomMembership.STATUS_REMOVED
        ).first()
        if not membership:
            return Response({"detail": "Not a member."}, status=status.HTTP_403_FORBIDDEN)
        if membership.role not in (ClassroomMembership.ROLE_ADMIN, "TEACHER"):
            return Response({"detail": "Teacher or admin access required."}, status=status.HTTP_403_FORBIDDEN)

        now = timezone.now()
        seven_days_ago = now - timedelta(days=7)

        # All students in the classroom.
        students = list(
            ClassroomMembership.objects.filter(
                classroom=classroom,
                role=ClassroomMembership.ROLE_STUDENT,
            ).select_related("user").order_by("user__last_name", "user__first_name")
        )
        student_ids = [m.user_id for m in students]
        student_map = {m.user_id: m.user for m in students}

        if not student_ids:
            return Response({
                "overdue_students": [],
                "inactive_students": [],
                "low_score_students": [],
                "completion_summary": [],
                "class_stats": {
                    "student_count": 0,
                    "assignment_count": 0,
                    "overall_completion_pct": 0,
                    "avg_assessment_score_pct": None,
                },
            })

        # All assignments in the classroom.
        assignments = list(
            Assignment.objects.filter(classroom=classroom)
            .select_related("assessment_homework__assessment_set")
            .order_by("due_at", "-created_at")
        )
        assignment_ids = [a.id for a in assignments]

        # All submissions by students in this classroom.
        submissions = list(
            Submission.objects.filter(
                assignment__classroom=classroom,
                student_id__in=student_ids,
            ).values("student_id", "assignment_id", "status", "updated_at")
        )
        # submitted_set[assignment_id] = set of student_ids who submitted
        submitted_set: dict[int, set] = defaultdict(set)
        last_activity: dict[int, object] = {}  # student_id → latest submission updated_at
        for s in submissions:
            if s["status"] in ("submitted", "reviewed", "returned"):
                submitted_set[s["assignment_id"]].add(s["student_id"])
            ts = s["updated_at"]
            prev = last_activity.get(s["student_id"])
            if prev is None or ts > prev:
                last_activity[s["student_id"]] = ts

        # Assessment attempt activity.
        try:
            from assessments.models import HomeworkAssignment as AssessHW, AssessmentAttempt, AssessmentResult

            hw_rows = list(
                AssessHW.objects.filter(classroom=classroom).select_related("assignment")
            )
            hw_by_id = {h.id: h for h in hw_rows}
            hw_assign_by_id = {h.assignment_id: h for h in hw_rows}

            assess_attempts = list(
                AssessmentAttempt.objects.filter(
                    homework_id__in=[h.id for h in hw_rows],
                    student_id__in=student_ids,
                ).values("student_id", "homework_id", "status", "started_at", "submitted_at")
            )
            assess_results = {
                r.attempt_id: r
                for r in AssessmentResult.objects.filter(
                    attempt__homework_id__in=[h.id for h in hw_rows],
                    attempt__student_id__in=student_ids,
                ).select_related("attempt")
            }

            # submitted_set update for assessment assignments.
            for att in assess_attempts:
                h = hw_by_id.get(att["homework_id"])
                if h and att["status"] in ("submitted", "graded"):
                    submitted_set[h.assignment_id].add(att["student_id"])
                ts = att.get("submitted_at") or att.get("started_at")
                if ts:
                    prev = last_activity.get(att["student_id"])
                    if prev is None or ts > prev:
                        last_activity[att["student_id"]] = ts

            # Average score per student across all assessment results.
            score_sum: dict[int, list[float]] = defaultdict(list)
            for r in assess_results.values():
                sid = r.attempt.student_id
                try:
                    score_sum[sid].append(float(r.percent))
                except (TypeError, ValueError):
                    pass
            avg_assess_score: dict[int, float] = {
                sid: sum(scores) / len(scores)
                for sid, scores in score_sum.items()
                if scores
            }
        except Exception:
            logger.exception("interventions: assessment hydration failed classroom_id=%s", classroom.pk)
            hw_assign_by_id = {}
            avg_assess_score = {}

        # ── Overdue students ──────────────────────────────────────────────────
        overdue_assignments = [
            a for a in assignments
            if a.due_at and a.due_at < now
        ]
        overdue_students: list[dict] = []
        seen_overdue: set[int] = set()
        for a in overdue_assignments:
            submitted = submitted_set.get(a.id, set())
            for sid in student_ids:
                if sid not in submitted and sid not in seen_overdue:
                    u = student_map[sid]
                    overdue_students.append({
                        "student_id": sid,
                        "email": u.email,
                        "first_name": u.first_name,
                        "last_name": u.last_name,
                        "overdue_count": sum(
                            1 for oa in overdue_assignments
                            if sid not in submitted_set.get(oa.id, set())
                        ),
                        "oldest_overdue_due_at": min(
                            (oa.due_at.isoformat() for oa in overdue_assignments
                             if oa.due_at and sid not in submitted_set.get(oa.id, set())),
                            default=None,
                        ),
                    })
                    seen_overdue.add(sid)
        # Sort by overdue_count descending.
        overdue_students.sort(key=lambda x: -x["overdue_count"])

        # ── Inactive students (no submission or attempt activity in 7 days) ───
        inactive_students: list[dict] = []
        for sid in student_ids:
            last = last_activity.get(sid)
            is_inactive = last is None or last < seven_days_ago
            if is_inactive:
                u = student_map[sid]
                inactive_students.append({
                    "student_id": sid,
                    "email": u.email,
                    "first_name": u.first_name,
                    "last_name": u.last_name,
                    "last_activity_at": last.isoformat() if last else None,
                    "days_inactive": (
                        (now - last).days if last else None
                    ),
                })
        inactive_students.sort(key=lambda x: (x["last_activity_at"] or "") )

        # ── Low-score students (avg assessment score < 60%) ───────────────────
        low_score_students: list[dict] = []
        for sid in student_ids:
            avg = avg_assess_score.get(sid)
            if avg is not None and avg < 60.0:
                u = student_map[sid]
                low_score_students.append({
                    "student_id": sid,
                    "email": u.email,
                    "first_name": u.first_name,
                    "last_name": u.last_name,
                    "avg_score_pct": round(avg, 1),
                })
        low_score_students.sort(key=lambda x: x["avg_score_pct"])

        # ── Completion summary per assignment ─────────────────────────────────
        n_students = len(student_ids)
        completion_summary = []
        for a in assignments:
            submitted = submitted_set.get(a.id, set())
            n_submitted = len(submitted & set(student_ids))
            completion_summary.append({
                "assignment_id": a.id,
                "title": a.title,
                "due_at": a.due_at.isoformat() if a.due_at else None,
                "is_overdue": bool(a.due_at and a.due_at < now),
                "is_assessment": a.id in hw_assign_by_id,
                "submitted_count": n_submitted,
                "student_count": n_students,
                "completion_pct": round(100.0 * n_submitted / n_students, 1) if n_students else 0.0,
            })

        # ── Class-level stats ─────────────────────────────────────────────────
        total_possible = n_students * len(assignments) if assignments else 0
        total_submitted = sum(
            len(submitted_set.get(a.id, set()) & set(student_ids))
            for a in assignments
        )
        overall_completion = (
            round(100.0 * total_submitted / total_possible, 1)
            if total_possible else 0.0
        )
        all_avg_scores = list(avg_assess_score.values())
        class_avg_score = round(mean(all_avg_scores), 1) if all_avg_scores else None

        return Response({
            "overdue_students": overdue_students,
            "inactive_students": inactive_students,
            "low_score_students": low_score_students,
            "completion_summary": completion_summary,
            "class_stats": {
                "student_count": n_students,
                "assignment_count": len(assignments),
                "overall_completion_pct": overall_completion,
                "avg_assessment_score_pct": class_avg_score,
            },
        })

    @action(detail=True, methods=["get"], permission_classes=[IsAuthenticatedAndNotFrozen], url_path="stream")
    def stream(self, request, pk=None):
        """
        Unified class feed: posts, new assignments, and submission events (mixed, newest first).
        """
        classroom = self.get_object()
        if not classroom.memberships.filter(user=request.user).exclude(
            status=ClassroomMembership.STATUS_REMOVED
        ).exists():
            return Response({"detail": "Not a member."}, status=status.HTTP_403_FORBIDDEN)
        qs = ClassroomStreamItem.objects.filter(classroom=classroom).select_related("actor").order_by("-created_at")
        paginator = StreamPagination()
        page = paginator.paginate_queryset(qs, request)
        items = list(page) if page is not None else list(qs[: StreamPagination.page_size])
        results = _build_stream_payload(items, request)
        if page is not None:
            return paginator.get_paginated_response(results)
        return Response({"count": len(results), "next": None, "previous": None, "results": results})

    @action(detail=True, methods=["get"], permission_classes=[IsAuthenticatedAndNotFrozen], url_path="student-workspace")
    def student_workspace(self, request, pk=None):
        """
        Student-centric slices: all classwork with workflow, due soon, recently graded, new posts.
        Teachers receive the same assignment list with ``workflow_status`` null.
        """
        classroom = self.get_object()
        if not classroom.memberships.filter(user=request.user).exclude(
            status=ClassroomMembership.STATUS_REMOVED
        ).exists():
            return Response({"detail": "Not a member."}, status=status.HTTP_403_FORBIDDEN)
        user = request.user
        is_student = classroom.memberships.filter(user=user, role=ClassroomMembership.ROLE_STUDENT).exists()
        now = timezone.now()
        week_end = now + timedelta(days=7)
        two_weeks_ago = now - timedelta(days=14)

        assignments_qs = (
            Assignment.objects.filter(classroom=classroom)
            .select_related("created_by", "assessment_homework__assessment_set")
            .order_by("-created_at")
        )
        # Students see only PUBLISHED work; staff see everything except ARCHIVED.
        if is_student:
            assignments_qs = assignments_qs.filter(status=Assignment.STATUS_PUBLISHED)
        else:
            assignments_qs = assignments_qs.exclude(status=Assignment.STATUS_ARCHIVED)
        subs_map = {}
        if is_student:
            subs_map = {
                s.assignment_id: s
                for s in Submission.objects.filter(student=user, assignment__classroom=classroom).select_related(
                    "review"
                )
            }

        # Assessment results keyed by Assignment.id for the current student.
        assessment_summary_by_assignment: dict[int, dict] = {}
        if is_student:
            try:
                from assessments.models import HomeworkAssignment as AssessHW, AssessmentAttempt, AssessmentResult

                hw_rows = list(
                    AssessHW.objects.filter(classroom=classroom).select_related("assessment_set", "assignment")
                )
                if hw_rows:
                    hw_by_assignment = {h.assignment_id: h for h in hw_rows}
                    atts = (
                        AssessmentAttempt.objects.filter(
                            student=user,
                            homework_id__in=[h.id for h in hw_rows],
                        )
                        .order_by("-started_at", "-id")
                    )
                    latest_by_hw: dict[int, AssessmentAttempt] = {}
                    for a in atts:
                        if a.homework_id not in latest_by_hw:
                            latest_by_hw[a.homework_id] = a
                    res_by_attempt = {
                        r.attempt_id: r
                        for r in AssessmentResult.objects.filter(attempt_id__in=[a.id for a in latest_by_hw.values()])
                    }
                    for assign_id, h in hw_by_assignment.items():
                        a = latest_by_hw.get(h.id)
                        r = res_by_attempt.get(a.id) if a else None
                        assessment_summary_by_assignment[assign_id] = {
                            "attempt_id": a.id if a else None,
                            "status": (a.status if a else "not_started"),
                            "submitted_at": a.submitted_at.isoformat() if a and a.submitted_at else None,
                            "total_time_seconds": int(a.total_time_seconds) if a else 0,
                            "result": (
                                {
                                    "score_points": str(r.score_points),
                                    "max_points": str(r.max_points),
                                    "percent": str(r.percent),
                                    "correct_count": r.correct_count,
                                    "total_questions": r.total_questions,
                                    "graded_at": r.graded_at.isoformat() if r.graded_at else None,
                                }
                                if r
                                else None
                            ),
                        }
            except Exception:
                logger.exception(
                    "assessment_workspace_hydration_failed classroom_id=%s user_id=%s",
                    classroom.pk,
                    request.user.pk,
                )

        def assignment_dict(a: Assignment):
            ser = AssignmentSerializer(a, context={"request": request})
            d = dict(ser.data)
            d["workflow_status"] = submission_workflow_status(subs_map.get(a.id)) if is_student else None
            if is_student:
                d["assessment"] = assessment_summary_by_assignment.get(a.id)
            return d

        your_assignments = [assignment_dict(a) for a in assignments_qs]

        due_soon = []
        if is_student:
            for a in assignments_qs:
                wf = submission_workflow_status(subs_map.get(a.id))
                if wf == "GRADED":
                    continue
                if a.due_at and now <= a.due_at <= week_end:
                    due_soon.append(assignment_dict(a))

        recently_graded = []
        if is_student:
            graded_subs = (
                Submission.objects.filter(
                    student=user,
                    assignment__classroom=classroom,
                    status=Submission.STATUS_REVIEWED,
                )
                .select_related("assignment", "review")
                .order_by("-review__reviewed_at")[:25]
            )
            for s in graded_subs:
                g = s.review
                recently_graded.append(
                    {
                        "assignment": {"id": s.assignment_id, "title": s.assignment.title},
                        "submission_id": s.id,
                        "workflow_status": submission_workflow_status(s),
                        "review": {
                            "grade": str(g.grade) if g.grade is not None else None,
                            "feedback": g.feedback,
                            "reviewed_at": g.reviewed_at.isoformat() if g.reviewed_at else None,
                        },
                    }
                )
            # Add assessment results (auto graded) to the same panel.
            try:
                for a in assignments_qs:
                    if a.id not in assessment_summary_by_assignment:
                        continue
                    summary = assessment_summary_by_assignment[a.id]
                    if not summary or not summary.get("result"):
                        continue
                    recently_graded.append(
                        {
                            "assignment": {"id": a.id, "title": a.title},
                            "submission_id": None,
                            "workflow_status": "GRADED",
                            "assessment_result": summary["result"],
                        }
                    )
            except Exception:
                pass

        new_posts = [
            ClassPostSerializer(p, context={"request": request}).data
            for p in ClassPost.objects.filter(classroom=classroom, created_at__gte=two_weeks_ago).order_by("-created_at")[
                :15
            ]
        ]

        return Response(
            {
                "your_assignments": your_assignments,
                "due_soon": due_soon,
                "recently_graded": recently_graded,
                "new_posts": new_posts,
                "is_student": is_student,
            }
        )


class JoinClassView(APIView):
    permission_classes = [IsAuthenticatedAndNotFrozen]

    def post(self, request):
        code = (request.data.get("join_code") or "").strip().upper()
        if not code:
            return Response({"detail": "Missing join_code."}, status=status.HTTP_400_BAD_REQUEST)
        classroom = Classroom.objects.filter(join_code=code, is_active=True).first()
        if not classroom:
            return Response({"detail": "Invalid class code."}, status=status.HTTP_400_BAD_REQUEST)

        if classroom.max_students is not None:
            current_students = classroom.memberships.filter(role="STUDENT").count()
            already_member = classroom.memberships.filter(user=request.user).exists()
            if not already_member and current_students >= classroom.max_students:
                return Response({"detail": "This group is full."}, status=status.HTTP_400_BAD_REQUEST)
        mem, created = ClassroomMembership.objects.get_or_create(
            classroom=classroom, user=request.user, defaults={"role": "STUDENT"}
        )
        dom = (
            acc_const.DOMAIN_MATH
            if classroom.subject == Classroom.SUBJECT_MATH
            else acc_const.DOMAIN_ENGLISH
        )
        UserAccess.objects.get_or_create(
            user=request.user,
            subject=dom,
            classroom=classroom,
            defaults={"granted_by": None},
        )
        logger.info(
            "classroom_join user_id=%s classroom_id=%s subject_domain=%s",
            request.user.pk,
            classroom.pk,
            dom,
        )
        return Response(
            {"joined": True, "role": mem.role, "classroom": ClassroomSerializer(classroom, context={"request": request}).data}
        )


def _clear_assignment_teacher_attachments(assignment: Assignment) -> None:
    """Remove primary and extra teacher-uploaded files from an assignment."""
    for ex in list(assignment.extra_attachments.all()):
        ex.delete()
    if assignment.attachment_file:
        assignment.attachment_file.delete(save=False)
    assignment.attachment_file = None
    assignment.save(update_fields=["attachment_file", "updated_at"])


class ClassPostViewSet(_ClassroomMemberGateMixin, ModelViewSet):
    permission_classes = [IsAuthenticatedAndNotFrozen]
    serializer_class = ClassPostSerializer
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_classroom(self):
        return get_object_or_404(Classroom, pk=self.kwargs["classroom_pk"])

    def get_queryset(self):
        classroom = self.get_classroom()
        # membership enforced
        if not classroom.memberships.filter(user=self.request.user).exclude(
            status=ClassroomMembership.STATUS_REMOVED
        ).exists():
            return ClassPost.objects.none()
        return ClassPost.objects.filter(classroom=classroom).select_related("author")

    def create(self, request, *args, **kwargs):
        classroom = self.get_classroom()
        if not has_cap(request.user, classroom, "can_post_announcement"):
            return Response({"detail": "Only the teaching team can post."}, status=status.HTTP_403_FORBIDDEN)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        post = serializer.save(classroom=classroom, author=request.user)
        return Response(self.get_serializer(post).data, status=status.HTTP_201_CREATED)

    def perform_update(self, serializer):
        classroom = serializer.instance.classroom
        if not has_cap(self.request.user, classroom, "can_post_announcement"):
            raise PermissionDenied("Only the teaching team can edit announcements.")
        serializer.save()

    def perform_destroy(self, instance):
        if not has_cap(self.request.user, instance.classroom, "can_post_announcement"):
            raise PermissionDenied("Only the teaching team can delete announcements.")
        instance.delete()


class AssignmentViewSet(_ClassroomMemberGateMixin, ModelViewSet):
    permission_classes = [IsAuthenticatedAndNotFrozen]
    serializer_class = AssignmentSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_classroom(self):
        return get_object_or_404(Classroom, pk=self.kwargs["classroom_pk"])

    def get_queryset(self):
        classroom = self.get_classroom()
        user = self.request.user
        if not classroom.memberships.filter(user=user).exclude(
            status=ClassroomMembership.STATUS_REMOVED
        ).exists():
            return Assignment.objects.none()
        qs = Assignment.objects.filter(classroom=classroom).select_related(
            "created_by", "mock_exam", "practice_test", "practice_test_pack", "module"
        ).prefetch_related("extra_attachments").annotate(submissions_count=Count("submissions"))
        is_staff = classroom.memberships.filter(
            user=user, role__in=ClassroomMembership.STAFF_ROLES
        ).exclude(status=ClassroomMembership.STATUS_REMOVED).exists()
        if not is_staff:
            # Students never see DRAFT or ARCHIVED assignments. Order newest-GIVEN first
            # (when it was published, falling back to creation) so freshly assigned work
            # is always at the top — re-publishing an old draft floats it up.
            return (
                qs.filter(status=Assignment.STATUS_PUBLISHED)
                .annotate(_given_at=Coalesce("published_at", "created_at"))
                .order_by("-_given_at", "-id")
            )
        include_archived = str(self.request.query_params.get("include_archived", "")).lower() in ("1", "true")
        return qs if include_archived else qs.exclude(status=Assignment.STATUS_ARCHIVED)

    def _manage_or_404(self, request, pk):
        """Fetch the assignment for lifecycle actions, bypassing the visibility filter,
        and require manage permission (any staff role)."""
        classroom = self.get_classroom()
        if not classroom.memberships.filter(
            user=request.user, role__in=ClassroomMembership.STAFF_ROLES
        ).exclude(status=ClassroomMembership.STATUS_REMOVED).exists():
            return None, Response({"detail": "You do not have permission to manage assignments."}, status=status.HTTP_403_FORBIDDEN)
        a = Assignment.objects.filter(pk=pk, classroom=classroom).first()
        if a is None:
            return None, Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return a, None

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticatedAndNotFrozen])
    def publish(self, request, classroom_pk=None, pk=None):
        a, err = self._manage_or_404(request, pk)
        if err:
            return err
        a.status = Assignment.STATUS_PUBLISHED
        a.archived_at = None
        if a.published_at is None:
            a.published_at = timezone.now()
        a.save(update_fields=["status", "archived_at", "published_at", "updated_at"])
        return Response({"id": a.id, "status": a.status})

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticatedAndNotFrozen])
    def archive(self, request, classroom_pk=None, pk=None):
        a, err = self._manage_or_404(request, pk)
        if err:
            return err
        a.status = Assignment.STATUS_ARCHIVED
        a.archived_at = timezone.now()
        a.save(update_fields=["status", "archived_at", "updated_at"])
        return Response({"id": a.id, "status": a.status})

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticatedAndNotFrozen])
    def unarchive(self, request, classroom_pk=None, pk=None):
        a, err = self._manage_or_404(request, pk)
        if err:
            return err
        a.status = Assignment.STATUS_PUBLISHED
        a.archived_at = None
        if a.published_at is None:
            a.published_at = timezone.now()
        a.save(update_fields=["status", "archived_at", "published_at", "updated_at"])
        return Response({"id": a.id, "status": a.status})

    def create(self, request, *args, **kwargs):
        classroom = self.get_classroom()
        if not has_cap(request.user, classroom, "can_manage_assignments"):
            return Response({"detail": "Only the teaching team can create assignments."}, status=status.HTTP_403_FORBIDDEN)

        # Gather uploaded files BEFORE running the serializer. The serializer has
        # `attachment_file` as a writable FileField — if we let it run, DRF will
        # consume ONE of the multi-uploaded files (and move its temp file to
        # storage) which then breaks the extras loop below when it tries to read
        # that same file's already-deleted temp path. We strip the field from
        # request.data and handle every file manually.
        files = list(request.FILES.getlist("attachment_file"))
        if not files:
            files = list(request.FILES.getlist("attachment_files"))
        if not files:
            files = list(request.FILES.getlist("attachment_file[]"))
        for f in files:
            validate_submission_upload(f)

        # Make a mutable copy of request.data with attachment_file removed so
        # the serializer doesn't consume any uploaded file. IMPORTANT: drop the file
        # keys BEFORE copying — QueryDict.copy() deep-copies its values, and a large
        # (temp-file-backed) upload is a BufferedRandom that is not picklable, so copying
        # with files still present raises "cannot pickle 'BufferedRandom'". Files are
        # handled manually below from request.FILES, so removing them here loses nothing.
        data = request.data
        if hasattr(data, "_mutable"):
            data._mutable = True
        for key in ("attachment_file", "attachment_files", "attachment_file[]"):
            try:
                if hasattr(data, "pop"):
                    data.pop(key, None)
            except Exception:
                pass
        data_copy = data.copy() if hasattr(data, "copy") else dict(data)

        serializer = self.get_serializer(data=data_copy)
        serializer.is_valid(raise_exception=True)
        assignment = serializer.save(classroom=classroom, created_by=request.user)

        # Save all attachment files manually (primary + extras) so we control
        # the order and avoid the serializer touching any temp file.
        if files:
            for f in files[1:]:
                AssignmentExtraAttachment.objects.create(assignment=assignment, file=f)
            assignment.attachment_file = files[0]
            assignment.save(update_fields=["attachment_file", "updated_at"])

        # Auto-assign pastpaper/practice test access to students
        try:
            grant_practice_test_library_access_for_assignment(assignment)
        except Exception:
            pass

        # Handle assessment_set_id — create linked HomeworkAssignment
        assessment_set_id = request.data.get("assessment_set_id")
        if assessment_set_id:
            try:
                from assessments.models import AssessmentSet, AssessmentSetVersion, HomeworkAssignment as AssessHW
                aset = AssessmentSet.objects.get(pk=int(assessment_set_id))
                pinned_version = (
                    AssessmentSetVersion.objects.filter(assessment_set=aset)
                    .order_by("-version_number")
                    .first()
                )
                # If the assessment set has no pinned version yet (newly created
                # set with questions but no version snapshot), create one now so
                # the homework can be assigned. Without a version, students
                # cannot start attempts.
                if pinned_version is None:
                    try:
                        from assessments.domain.publish_service import publish_assessment_set
                        pinned_version = publish_assessment_set(
                            set_id=aset.pk, actor=request.user
                        )
                    except Exception:
                        logger.exception(
                            "publish_assessment_set failed for assessment_set_id=%s; "
                            "assigning without pinned_version",
                            aset.pk,
                        )
                with transaction.atomic():
                    AssessHW.objects.create(
                        classroom=classroom,
                        assessment_set=aset,
                        assignment=assignment,
                        assigned_by=request.user,
                        set_version=pinned_version,
                    )
            except IntegrityError:
                logger.exception(
                    "IntegrityError creating assessment homework for assignment_id=%s set_id=%s",
                    assignment.pk, assessment_set_id,
                )
            except Exception:
                logger.exception(
                    "Failed to create assessment homework for assignment_id=%s set_id=%s",
                    assignment.pk, assessment_set_id,
                )

        return Response(self.get_serializer(assignment).data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        # Same multi-upload issue as create — strip attachment_file from
        # request.data so the serializer doesn't consume one of the files.
        files = list(request.FILES.getlist("attachment_file"))
        if not files:
            files = list(request.FILES.getlist("attachment_files"))
        if not files:
            files = list(request.FILES.getlist("attachment_file[]"))
        for f in files:
            validate_submission_upload(f)

        # Make a sanitized copy of request.data without attachment_file fields,
        # and temporarily swap it in so the super().update() serializer call
        # doesn't see them. Drop the file keys BEFORE copying — copying a QueryDict
        # deep-copies its values and a large (temp-file-backed) upload is a non-picklable
        # BufferedRandom, which would raise "cannot pickle 'BufferedRandom'". Files are
        # handled manually below from request.FILES.
        original_data = request.data
        if hasattr(original_data, "_mutable"):
            original_data._mutable = True
        for key in ("attachment_file", "attachment_files", "attachment_file[]"):
            try:
                if hasattr(original_data, "pop"):
                    original_data.pop(key, None)
            except Exception:
                pass
        sanitized = original_data.copy() if hasattr(original_data, "copy") else dict(original_data)
        # Override request._full_data so DRF reads our sanitized version
        try:
            request._full_data = sanitized
        except Exception:
            pass

        super().update(request, *args, **kwargs)
        assignment = self.get_object()
        replace_all = str(request.query_params.get("replace_attachments", "")).lower() in ("1", "true", "yes", "on")
        if replace_all:
            _clear_assignment_teacher_attachments(assignment)
        if files:
            for f in files[1:]:
                AssignmentExtraAttachment.objects.create(assignment=assignment, file=f)
            assignment.attachment_file = files[0]
            assignment.save(update_fields=["attachment_file", "updated_at"])
        return Response(self.get_serializer(assignment).data)

    def partial_update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)

    def perform_destroy(self, instance):
        if not has_cap(self.request.user, instance.classroom, "can_delete_assignment"):
            raise PermissionDenied("Only a teacher or owner can delete assignments (TAs can archive).")
        instance.delete()

    def perform_update(self, serializer):
        if not has_cap(self.request.user, serializer.instance.classroom, "can_manage_assignments"):
            raise PermissionDenied("Only the teaching team can edit assignments.")
        serializer.save()

    def _parse_remove_file_ids(self, request) -> list[int]:
        raw = request.data.get("remove_file_ids")
        if raw in (None, "", []):
            return []
        if isinstance(raw, list):
            ids = raw
        else:
            s = str(raw).strip()
            try:
                ids = json.loads(s) if s.startswith("[") else [int(x) for x in s.split(",") if x.strip().isdigit()]
            except (json.JSONDecodeError, TypeError, ValueError):
                return []
        out: list[int] = []
        for x in ids:
            try:
                out.append(int(x))
            except (TypeError, ValueError):
                continue
        return out

    @action(
        detail=True,
        methods=["post"],
        url_path="submit",
        throttle_classes=[
            HomeworkSubmitThrottle,
            HomeworkSubmitGlobalThrottle,
            HomeworkSubmitClassThrottle,
        ],
    )
    def submit(self, request, classroom_pk=None, pk=None):
        classroom = self.get_classroom()
        if not classroom.memberships.filter(user=request.user).exclude(
            status=ClassroomMembership.STATUS_REMOVED
        ).exists():
            return Response({"detail": "Not a member."}, status=status.HTTP_403_FORBIDDEN)
        assignment = get_object_or_404(Assignment, pk=pk, classroom=classroom)

        student = request.user
        if not classroom.memberships.filter(user=student, role=ClassroomMembership.ROLE_STUDENT).exists():
            return Response(
                {"detail": "Only students can submit homework for this assignment."},
                status=status.HTTP_403_FORBIDDEN,
            )

        new_files = list(request.FILES.getlist("files"))
        if not new_files:
            new_files = list(request.FILES.getlist("file"))
        for f in new_files:
            try:
                validate_submission_upload(f)
            except DjangoValidationError as e:
                msg = e.messages[0] if getattr(e, "messages", None) else str(e)
                return Response({"detail": msg}, status=status.HTTP_400_BAD_REQUEST)

        remove_ids = self._parse_remove_file_ids(request)

        try:
            sub, _ = Submission.objects.get_or_create(assignment=assignment, student=student)
        except IntegrityError:
            sub = Submission.objects.get(assignment=assignment, student=student)

        batch_max = max_batch_upload_bytes()
        batch_total = 0
        for f in new_files:
            sz = getattr(f, "size", None)
            if sz is None:
                try:
                    pos = f.tell()
                    f.seek(0, os.SEEK_END)
                    sz = f.tell()
                    f.seek(pos)
                except (OSError, AttributeError):
                    sz = 0
            batch_total += int(sz or 0)
        if batch_total > batch_max:
            record_homework_submit_error()
            return Response(
                {
                    "detail": (
                        f"Total upload size for this request ({batch_total} bytes) exceeds "
                        f"the maximum allowed ({batch_max} bytes)."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = SubmitSerializer(
            data=request.data,
            context={
                "new_files_count": len(new_files),
                "submission_id": sub.pk,
                "remove_file_ids": remove_ids,
            },
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        record_homework_submit_attempt()

        past_due = assignment.due_at and timezone.now() > assignment.due_at

        resolved_attempt = None
        if "attempt_id" in data:
            attempt_id = data.get("attempt_id")
            if attempt_id is None:
                resolved_attempt = None
            else:
                att = TestAttempt.objects.filter(id=attempt_id, student=student).first()
                if not att:
                    record_homework_submit_error()
                    return Response(
                        {"detail": "Invalid attempt id for this student."}, status=status.HTTP_400_BAD_REQUEST
                    )
                targets = assignment_target_practice_test_ids(assignment)
                if targets and att.practice_test_id not in targets:
                    record_homework_submit_error()
                    return Response(
                        {"detail": "That attempt does not belong to a practice test linked to this homework."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                resolved_attempt = att

        file_tokens_list: list[str] = data.get("file_tokens_list") or []
        expected_revision = data.get("expected_revision")

        max_files = max_files_per_submission()
        remaining_slots = SubmissionFile.objects.filter(submission=sub).exclude(pk__in=remove_ids).count()
        if remaining_slots + len(new_files) > max_files:
            record_homework_submit_error()
            return Response(
                {
                    "detail": (
                        f"Too many files for one submission (would exceed {max_files}). "
                        "Remove files or submit fewer at once."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        staged_paths: list[str] = []
        staged_uploads = []
        for i, uf in enumerate(new_files):
            tok = file_tokens_list[i] if i < len(file_tokens_list) else None
            if tok and SubmissionFile.objects.filter(submission_id=sub.pk, upload_token=tok[:64]).exists():
                continue
            su = stream_upload_to_storage(sub.pk, uf, upload_token=tok)
            staged_uploads.append(su)
            staged_paths.append(su.storage_path)
            HomeworkStagedUpload.objects.update_or_create(
                submission_id=sub.pk,
                storage_path=su.storage_path,
                defaults={
                    "upload_token": (su.upload_token or "")[:64],
                    "content_sha256": su.content_sha256 or "",
                    "deterministic": True,
                    "status": HomeworkStagedUpload.STATUS_STAGING,
                },
            )

        do_submit = data.get("submit", True)

        def commit_all():
            nonlocal sub
            with transaction.atomic():
                s = Submission.objects.select_for_update().get(pk=sub.pk)
                if expected_revision is not None and int(expected_revision) != s.revision:
                    raise SubmitFlowError(_revision_conflict_response(s))
                try:
                    assert_student_edit_allowed(s)
                except DRFValidationError as e:
                    raise SubmitFlowError(Response(e.detail, status=status.HTTP_400_BAD_REQUEST))
                if past_due and s.status != Submission.STATUS_RETURNED:
                    raise SubmitFlowError(
                        Response(
                            {"detail": "The due date has passed. You can no longer change your submission."},
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                    )

                prev_attempt_id = s.attempt_id
                to_delete = list(SubmissionFile.objects.filter(pk__in=remove_ids, submission=s))
                delete_pks = {sf.pk for sf in to_delete}
                attempt_changed = False
                if "attempt_id" in data:
                    new_att = resolved_attempt
                    if s.attempt_id != getattr(new_att, "id", None):
                        attempt_changed = True
                    s.attempt = new_att

                remaining_qs = s.files.exclude(pk__in=delete_pks) if delete_pks else s.files.all()
                remaining_file_count = remaining_qs.count()
                existing_sha = set(
                    remaining_qs.exclude(content_sha256="").values_list("content_sha256", flat=True)
                )
                existing_tokens = set(
                    remaining_qs.exclude(upload_token="").values_list("upload_token", flat=True)
                )

                would_attach = 0
                for su in staged_uploads:
                    if su.content_sha256 and su.content_sha256 in existing_sha:
                        abandon_staged_uploads(s.pk, [su.storage_path])
                        continue
                    tok = (su.upload_token or "")[:64]
                    if tok and tok in existing_tokens:
                        abandon_staged_uploads(s.pk, [su.storage_path])
                        continue
                    would_attach += 1
                    if su.content_sha256:
                        existing_sha.add(su.content_sha256)
                    if tok:
                        existing_tokens.add(tok)

                prospective_file_count = remaining_file_count + would_attach
                if do_submit and prospective_file_count == 0 and s.attempt_id is None:
                    raise SubmitFlowError(
                        Response(
                            {"detail": "Submit at least one file or link a test attempt."},
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                    )

                prev_status = s.status
                submit_will_transition = do_submit and prev_status in (
                    Submission.STATUS_DRAFT,
                    Submission.STATUS_RETURNED,
                )
                need_revision_bump = (
                    bool(to_delete)
                    or attempt_changed
                    or would_attach > 0
                    or submit_will_transition
                )
                if need_revision_bump:
                    s.revision += 1
                rev = s.revision

                for sf in to_delete:
                    audit_submission_event(
                        s.pk,
                        request.user.pk,
                        SubmissionAuditEvent.EVENT_FILE_REMOVE,
                        {"file_id": sf.pk},
                        submission_revision=rev,
                    )
                    sf.delete()

                if attempt_changed:
                    audit_submission_event(
                        s.pk,
                        request.user.pk,
                        SubmissionAuditEvent.EVENT_ATTEMPT_CHANGE,
                        {
                            "from_attempt_id": prev_attempt_id,
                            "to_attempt_id": s.attempt_id,
                        },
                        submission_revision=rev,
                    )

                for su in staged_uploads:
                    if SubmissionFile.objects.filter(submission=s, content_sha256=su.content_sha256).exists():
                        abandon_staged_uploads(s.pk, [su.storage_path])
                        continue
                    tok = (su.upload_token or "")[:64]
                    if tok and SubmissionFile.objects.filter(submission=s, upload_token=tok).exists():
                        abandon_staged_uploads(s.pk, [su.storage_path])
                        continue
                    row = SubmissionFile(
                        submission=s,
                        file_name=su.file_name,
                        file_type=su.file_type,
                        content_sha256=su.content_sha256,
                        upload_token=tok,
                    )
                    row.file.name = su.storage_path
                    try:
                        row.save()
                    except IntegrityError:
                        abandon_staged_uploads(s.pk, [su.storage_path])
                        continue
                    HomeworkStagedUpload.objects.filter(
                        submission_id=s.pk,
                        storage_path=su.storage_path,
                    ).update(status=HomeworkStagedUpload.STATUS_ATTACHED, content_sha256=su.content_sha256 or "")
                    audit_submission_event(
                        s.pk,
                        request.user.pk,
                        SubmissionAuditEvent.EVENT_FILE_ADD,
                        {"submission_file_id": row.pk, "file_name": row.file_name},
                        submission_revision=rev,
                    )

                if do_submit:
                    try:
                        s.mark_submitted()
                    except ValueError as e:
                        raise SubmitFlowError(Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST))
                    _audit(
                        s,
                        request.user,
                        SubmissionAuditEvent.EVENT_STATUS_CHANGE,
                        {"from": prev_status, "to": s.status},
                    )

                s.save()
                sub = s

        try:
            db_retry_operation(commit_all)
        except SubmitFlowError as e:
            record_homework_submit_error()
            abandon_staged_uploads(sub.pk, staged_paths)
            return e.response
        except Exception:
            record_homework_submit_error()
            abandon_staged_uploads(sub.pk, staged_paths)
            raise

        record_homework_submit_success()
        sub = (
            Submission.objects.filter(pk=sub.pk)
            .select_related("student", "attempt", "attempt__practice_test", "review", "review__teacher")
            .prefetch_related("files")
            .first()
        )
        return Response(SubmissionSerializer(sub, context={"request": request}).data)

    @action(detail=True, methods=["get"], url_path="my-submission")
    def my_submission(self, request, classroom_pk=None, pk=None):
        classroom = self.get_classroom()
        if not classroom.memberships.filter(user=request.user).exclude(
            status=ClassroomMembership.STATUS_REMOVED
        ).exists():
            return Response({"detail": "Not a member."}, status=status.HTTP_403_FORBIDDEN)
        assignment = get_object_or_404(Assignment, pk=pk, classroom=classroom)
        if classroom.memberships.filter(
            user=request.user, role=ClassroomMembership.ROLE_STUDENT
        ).exists():
            try:
                sync_practice_submission_for_assignment(request.user, assignment)
            except Exception:
                logger.exception(
                    "sync_practice_submission_failed assignment_id=%s user_id=%s",
                    assignment.pk,
                    request.user.pk,
                )
            # Also lazy-sync assessment homework
            hw_link = getattr(assignment, "assessment_homework", None)
            if hw_link is not None:
                from assessments.models import AssessmentAttempt
                from classes.homework_auto_submit import sync_assessment_submission

                att = AssessmentAttempt.objects.filter(
                    homework=hw_link,
                    student=request.user,
                    status__in=[AssessmentAttempt.STATUS_SUBMITTED, AssessmentAttempt.STATUS_GRADED],
                ).order_by("-submitted_at").first()
                if att:
                    try:
                        sync_assessment_submission(att)
                    except Exception:
                        logger.exception(
                            "sync_assessment_submission_failed assignment_id=%s user_id=%s",
                            assignment.pk,
                            request.user.pk,
                        )
        sub = (
            Submission.objects.filter(assignment=assignment, student=request.user)
            .select_related("attempt", "attempt__practice_test", "review", "review__teacher")
            .prefetch_related("files")
            .first()
        )
        if not sub:
            return Response({}, status=status.HTTP_200_OK)
        return Response(SubmissionSerializer(sub, context={"request": request}).data)

    @action(detail=True, methods=["get"], url_path="submissions")
    def submissions(self, request, classroom_pk=None, pk=None):
        classroom = self.get_classroom()
        if not has_cap(request.user, classroom, "can_grade"):
            return Response({"detail": "Only the teaching team can view submissions."}, status=status.HTTP_403_FORBIDDEN)
        assignment = get_object_or_404(Assignment, pk=pk, classroom=classroom)
        if assignment_target_practice_test_ids(assignment):
            student_ids = classroom.memberships.filter(
                role=ClassroomMembership.ROLE_STUDENT
            ).values_list("user_id", flat=True)
            from django.contrib.auth import get_user_model

            User = get_user_model()
            for uid in student_ids:
                u = User.objects.filter(pk=uid).first()
                if not u:
                    continue
                try:
                    sync_practice_submission_for_assignment(u, assignment)
                except Exception:
                    logger.exception(
                        "sync_practice_submission_failed assignment_id=%s student_id=%s",
                        assignment.pk,
                        uid,
                    )

        # Lazy-sync assessment homework submissions
        hw_link = getattr(assignment, "assessment_homework", None)
        if hw_link is not None:
            from assessments.models import AssessmentAttempt
            from classes.homework_auto_submit import sync_assessment_submission

            submitted_attempts = AssessmentAttempt.objects.filter(
                homework=hw_link,
                status__in=[AssessmentAttempt.STATUS_SUBMITTED, AssessmentAttempt.STATUS_GRADED],
            ).select_related("student")
            for att in submitted_attempts:
                try:
                    sync_assessment_submission(att)
                except Exception:
                    logger.exception(
                        "sync_assessment_submission_failed assignment_id=%s attempt_id=%s",
                        assignment.pk,
                        att.pk,
                    )
        qs = (
            Submission.objects.filter(assignment=assignment)
            .select_related("student", "attempt", "attempt__practice_test", "review", "review__teacher")
            .prefetch_related("files")
        )
        return Response(SubmissionSerializer(qs, many=True, context={"request": request}).data)


class SubmissionAdminViewSet(ReadOnlyModelViewSet):
    """
    Grading: list/retrieve only for submissions in classes where the user is ADMIN.
    """

    permission_classes = [IsAuthenticatedAndNotFrozen]
    serializer_class = SubmissionSerializer

    def get_queryset(self):
        user = self.request.user
        # Graders = the teaching team (TA + Teacher + Owner) per the capability matrix.
        admin_class_ids = ClassroomMembership.objects.filter(
            user=user, role__in=ClassroomMembership.STAFF_ROLES
        ).values_list("classroom_id", flat=True)
        return (
            Submission.objects.filter(assignment__classroom_id__in=admin_class_ids)
            .select_related(
                "assignment__classroom", "student", "attempt", "attempt__practice_test", "review", "review__teacher"
            )
            .prefetch_related("files")
            .distinct()
        )

    def get_object(self):
        queryset = self.filter_queryset(self.get_queryset())
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        lookup = self.kwargs.get(lookup_url_kwarg)
        try:
            return queryset.get(**{self.lookup_field: lookup})
        except Submission.DoesNotExist:
            if Submission.objects.filter(pk=lookup).exists():
                raise PermissionDenied(detail="You are not allowed to access this submission.")
            raise NotFound()

    def list(self, request, *args, **kwargs):
        """Avoid accidental bulk export; grading uses per-assignment submissions/ or retrieve by id."""
        return Response(
            {"detail": "Listing all submissions is not supported. Use class assignment submissions."},
            status=status.HTTP_403_FORBIDDEN,
        )

    def get_classroom(self):
        submission = self.get_object()
        return submission.assignment.classroom

    @action(detail=True, methods=["post"], url_path="grade")
    def grade(self, request, pk=None):
        submission = self.get_object()
        classroom = submission.assignment.classroom
        if not has_cap(request.user, classroom, "can_grade"):
            return Response({"detail": "Only the teaching team can grade."}, status=status.HTTP_403_FORBIDDEN)

        serializer = SubmissionReviewUpsertSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        review = None
        prev_status = None

        def _grade_tx():
            nonlocal submission, review, prev_status
            with transaction.atomic():
                submission = (
                    Submission.objects.select_for_update()
                    .select_related("assignment", "assignment__classroom")
                    .get(pk=submission.pk)
                )
                expected_revision = data.get("expected_revision")
                if expected_revision is not None and int(expected_revision) != submission.revision:
                    raise SubmitFlowError(_revision_conflict_response(submission))
                try:
                    assert_teacher_grade_allowed(submission)
                except DRFValidationError as e:
                    raise SubmitFlowError(Response(e.detail, status=status.HTTP_400_BAD_REQUEST))

                prev_status = submission.status
                review, _ = SubmissionReview.objects.get_or_create(
                    submission=submission, defaults={"teacher": request.user}
                )
                if "grade" in data:
                    review.grade = data["grade"]
                if "feedback" in data:
                    review.feedback = data["feedback"]
                review.teacher = request.user
                review.save()

                submission.status = Submission.STATUS_REVIEWED
                submission.revision += 1
                submission.save(update_fields=["status", "updated_at", "revision"])

                _audit(
                    submission,
                    request.user,
                    SubmissionAuditEvent.EVENT_REVIEW_UPSERT,
                    {
                        "previous_status": prev_status,
                        "grade": str(review.grade) if review.grade is not None else None,
                        "feedback_chars": len(review.feedback or ""),
                    },
                )
                if prev_status != Submission.STATUS_REVIEWED:
                    _audit(
                        submission,
                        request.user,
                        SubmissionAuditEvent.EVENT_STATUS_CHANGE,
                        {"from": prev_status, "to": submission.status},
                    )

        try:
            db_retry_operation(_grade_tx)
        except SubmitFlowError as e:
            return e.response

        classroom_id = submission.assignment.classroom_id
        student_id = submission.student_id
        transaction.on_commit(lambda: _emit_grade_realtime(classroom_id, student_id))

        submission = (
            Submission.objects.filter(pk=submission.pk)
            .select_related("student", "attempt", "attempt__practice_test", "review", "review__teacher")
            .prefetch_related("files")
            .first()
        )
        return Response(SubmissionSerializer(submission, context={"request": request}).data)

    @action(detail=True, methods=["post"], url_path="return")
    def return_for_revision(self, request, pk=None):
        """Teacher returns submitted/reviewed work so the student can edit and resubmit."""
        submission = self.get_object()
        classroom = submission.assignment.classroom
        if not has_cap(request.user, classroom, "can_grade"):
            return Response({"detail": "Only the teaching team can return submissions."}, status=status.HTTP_403_FORBIDDEN)

        ser = SubmissionReturnSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        note = (ser.validated_data.get("note") or "").strip()

        prev = None

        def _return_tx():
            nonlocal submission, prev
            with transaction.atomic():
                submission = (
                    Submission.objects.select_for_update()
                    .select_related("assignment", "assignment__classroom")
                    .get(pk=submission.pk)
                )
                expected_revision = ser.validated_data.get("expected_revision")
                if expected_revision is not None and int(expected_revision) != submission.revision:
                    raise SubmitFlowError(_revision_conflict_response(submission))
                try:
                    assert_teacher_return_allowed(submission)
                except DRFValidationError as e:
                    raise SubmitFlowError(Response(e.detail, status=status.HTTP_400_BAD_REQUEST))

                prev = submission.status
                submission.status = Submission.STATUS_RETURNED
                submission.returned_at = timezone.now()
                submission.return_note = note[:10000]
                submission.revision += 1
                submission.save(
                    update_fields=["status", "returned_at", "return_note", "updated_at", "revision"]
                )

                _audit(
                    submission,
                    request.user,
                    SubmissionAuditEvent.EVENT_RETURN,
                    {"from_status": prev, "to_status": Submission.STATUS_RETURNED, "note": note[:5000]},
                )

        try:
            db_retry_operation(_return_tx)
        except SubmitFlowError as e:
            return e.response

        cid = submission.assignment.classroom_id
        sid = submission.student_id
        transaction.on_commit(lambda: _emit_return_realtime(cid, sid))

        submission = (
            Submission.objects.filter(pk=submission.pk)
            .select_related("student", "attempt", "attempt__practice_test", "review", "review__teacher")
            .prefetch_related("files")
            .first()
        )
        return Response(SubmissionSerializer(submission, context={"request": request}).data)

    @action(detail=True, methods=["get"], url_path="audit-log")
    def audit_log(self, request, pk=None):
        submission = self.get_object()
        classroom = submission.assignment.classroom
        is_teacher = has_cap(request.user, classroom, "can_grade")
        is_owner = request.user.pk == submission.student_id
        if not (is_teacher or is_owner):
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)
        qs = submission.audit_events.all()[:300]
        return Response(SubmissionAuditEventReadSerializer(qs, many=True).data)


class ClassCommentListCreateView(APIView):
    """
    Threaded comments on announcements or classwork.
    GET: ?target_type=post|assignment&target_id=<pk>
    POST: { target_type, target_id, content, parent? }
    """

    permission_classes = [IsAuthenticatedAndNotFrozen]

    def get(self, request, classroom_pk):
        classroom = get_object_or_404(Classroom, pk=classroom_pk)
        if not classroom.memberships.filter(user=request.user).exclude(
            status=ClassroomMembership.STATUS_REMOVED
        ).exists():
            return Response({"detail": "Not a member."}, status=status.HTTP_403_FORBIDDEN)
        tt = (request.query_params.get("target_type") or "").strip().lower()
        if tt == "post":
            tt = ClassComment.TARGET_POST
        elif tt == "assignment":
            tt = ClassComment.TARGET_ASSIGNMENT
        tid = request.query_params.get("target_id")
        if tt not in (ClassComment.TARGET_POST, ClassComment.TARGET_ASSIGNMENT) or not tid:
            return Response(
                {"detail": "Query params target_type (post|assignment) and target_id are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            tid = int(tid)
        except (TypeError, ValueError):
            return Response({"detail": "Invalid target_id."}, status=status.HTTP_400_BAD_REQUEST)
        if tt == ClassComment.TARGET_POST:
            if not ClassPost.objects.filter(pk=tid, classroom=classroom).exists():
                return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        elif not Assignment.objects.filter(pk=tid, classroom=classroom).exists():
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        qs = ClassComment.objects.filter(classroom=classroom, target_type=tt, target_id=tid).select_related(
            "author", "parent"
        )
        return Response(ClassCommentSerializer(qs, many=True).data)

    def post(self, request, classroom_pk):
        classroom = get_object_or_404(Classroom, pk=classroom_pk)
        if not classroom.memberships.filter(user=request.user).exclude(
            status=ClassroomMembership.STATUS_REMOVED
        ).exists():
            return Response({"detail": "Not a member."}, status=status.HTTP_403_FORBIDDEN)
        ser = ClassCommentSerializer(data=request.data, context={"classroom": classroom, "request": request})
        ser.is_valid(raise_exception=True)
        c = ser.save(classroom=classroom, author=request.user)
        # Realtime delivery hint: refetch comments from canonical endpoint.
        from realtime.services import emit_to_classroom_members, emit_to_user

        emit_to_classroom_members(
            classroom_id=classroom.pk,
            event_type="comments.updated",
            payload={
                "classroom_id": classroom.pk,
                "target_type": c.target_type,
                "target_id": c.target_id,
                "comment_id": c.pk,
                "parent_id": c.parent_id,
                "reason": "comment",
            },
        )
        if c.parent_id and c.parent and c.parent.author_id and c.parent.author_id != request.user.pk:
            emit_to_user(
                user_id=c.parent.author_id,
                event_type="notifications.updated",
                payload={"reason": "comment_reply", "classroom_id": classroom.pk},
            )
        return Response(ClassCommentSerializer(c, context={"request": request}).data, status=status.HTTP_201_CREATED)


class OpsStatsView(APIView):
    """
    GET /classes/ops/stats/
    Aggregate statistics for the ops dashboard — replaces N individual
    listAssignments() calls with a single annotated query.

    Returns:
      total_classrooms    int   all classrooms visible to the actor
      managed_classrooms  int   classrooms where actor has ADMIN role
      total_assignments   int   across all managed classrooms
      active_assignments  int   assignments without completed_at set
    """

    permission_classes = [IsAuthenticatedAndNotFrozen]

    def get(self, request):
        if not is_global_scope_staff(request.user):
            # Fall back to only classrooms the user admins
            managed_ids = ClassroomMembership.objects.filter(
                user=request.user, role="ADMIN"
            ).values_list("classroom_id", flat=True)
            total_classrooms = Classroom.objects.filter(
                memberships__user=request.user,
                memberships__status__in=ClassroomMembership.NON_REMOVED_STATUSES,
            ).distinct().count()
        else:
            managed_ids = ClassroomMembership.objects.filter(
                user=request.user, role="ADMIN"
            ).values_list("classroom_id", flat=True)
            total_classrooms = Classroom.objects.count()

        managed_count = len(managed_ids)

        qs = Assignment.objects.filter(classroom_id__in=managed_ids)
        total_assignments = qs.count()
        # "active" = has a future or no due date (no completed_at field exists on Assignment)
        active_assignments = qs.filter(
            Q(due_at__isnull=True) | Q(due_at__gte=timezone.now())
        ).count()

        return Response(
            {
                "total_classrooms": total_classrooms,
                "managed_classrooms": managed_count,
                "total_assignments": total_assignments,
                "active_assignments": active_assignments,
            }
        )


class OpsAttentionView(APIView):
    """
    GET /classes/ops/attention/
    Returns actionable signals for the ops dashboard:
      - overdue_assignments: top-5 assignments past due_at, with classroom name + days overdue
      - overdue_count: total count of overdue assignments visible to this actor
      - scoring_failures: count of AssessmentAttempts in GRADING_FAILED state
    """

    permission_classes = [IsAuthenticatedAndNotFrozen]

    def get(self, request):
        now = timezone.now()

        if is_global_scope_staff(request.user):
            all_classroom_ids = Classroom.objects.values_list("id", flat=True)
        else:
            all_classroom_ids = ClassroomMembership.objects.filter(
                user=request.user, role="ADMIN"
            ).values_list("classroom_id", flat=True)

        # Overdue = has a due_at in the past
        overdue_qs = (
            Assignment.objects.filter(
                classroom_id__in=all_classroom_ids,
                due_at__lt=now,
            )
            .select_related("classroom")
            .order_by("due_at")  # oldest first
        )
        overdue_count = overdue_qs.count()
        top_overdue = overdue_qs[:5]

        overdue_items = []
        for a in top_overdue:
            delta = now - a.due_at
            overdue_items.append(
                {
                    "id": a.id,
                    "title": a.title,
                    "classroom_name": a.classroom.name,
                    "classroom_id": a.classroom_id,
                    "due_at": a.due_at.isoformat(),
                    "days_overdue": delta.days,
                }
            )

        # Scoring failures — cross-app import, safe to do here (assessments is a stable dep)
        scoring_failures = 0
        try:
            from assessments.models import AssessmentAttempt
            scoring_failures = AssessmentAttempt.objects.filter(
                grading_status=AssessmentAttempt.GRADING_FAILED
            ).count()
        except Exception:
            pass

        return Response(
            {
                "overdue_assignments": overdue_items,
                "overdue_count": overdue_count,
                "scoring_failures": scoring_failures,
            }
        )

