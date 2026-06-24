"""Classroom results aggregation (read-only view layer).

GET /api/classes/<pk>/midterm-results/   per-midterm aggregates + per-student rows
GET /api/classes/<pk>/results/           unified results across assessments, midterms,
                                          past papers (filters: student, type, date range)

Reads only existing result data — TestAttempt (midterm/practice), AssessmentAttempt+
AssessmentResult (assessment homework), and classes.Submission (file/practice homework).
No engine, scoring, or schema changes. Metrics that cannot be computed from real data
are returned as null (the UI hides them); nothing is estimated.
"""

from __future__ import annotations

from rest_framework import status as http
from rest_framework.response import Response

from access.models import ResourceAccessGrant
from access.resources import RT_MIDTERM

from .capabilities import classroom_capabilities
from .models import Assignment, ClassroomMembership, Submission
from .views_rankings import _ClassroomScopedView, _display_name


def _active_students(classroom):
    return list(
        classroom.memberships.filter(
            role=ClassroomMembership.ROLE_STUDENT, status=ClassroomMembership.STATUS_ACTIVE
        ).select_related("user")
    )


def _agg(scores: list[float]) -> dict:
    if not scores:
        return {"average": None, "highest": None, "lowest": None}
    return {
        "average": round(sum(scores) / len(scores), 1),
        "highest": max(scores),
        "lowest": min(scores),
    }


class ClassroomMidtermResultsView(_ClassroomScopedView):
    """Per-midterm classroom performance, strictly scoped to classroom membership."""

    def get(self, request, classroom_pk):
        classroom = self.get_classroom()
        caps = classroom_capabilities(request.user, classroom)
        if not caps.is_staff:
            return Response({"detail": "Staff only."}, status=http.HTTP_403_FORBIDDEN)

        from exams.models import MockExam, TestAttempt

        students = _active_students(classroom)
        student_ids = [m.user_id for m in students]
        name_by_id = {m.user_id: _display_name(m.user) for m in students}

        # Midterms assigned to THIS classroom (grant persists past the post-result access revoke).
        midterm_ids = list(
            ResourceAccessGrant.objects.filter(
                classroom_id=classroom.pk,
                scope=ResourceAccessGrant.SCOPE_RESOURCE,
                resource_type=RT_MIDTERM,
            ).values_list("resource_id", flat=True).distinct()
        )
        midterms = MockExam.objects.filter(pk__in=midterm_ids, kind=MockExam.KIND_MIDTERM)

        out = []
        for mid in midterms:
            attempts = TestAttempt.objects.filter(mock_exam=mid, student_id__in=student_ids)
            by_student: dict[int, list] = {}
            for a in attempts:
                by_student.setdefault(a.student_id, []).append(a)

            rows, completed_scores = [], []
            started = completed = 0
            for sid in student_ids:
                atts = sorted(by_student.get(sid, []), key=lambda x: x.created_at)
                if not atts:
                    rows.append({"student_id": sid, "student": name_by_id[sid], "state": "not_started",
                                 "score": None, "attempt_date": None, "attempt_count": 0})
                    continue
                started += 1
                done = [a for a in atts if a.is_completed]
                latest = (done or atts)[-1]
                state = "completed" if done else "in_progress"
                if done:
                    completed += 1
                    if latest.score is not None:
                        completed_scores.append(float(latest.score))
                rows.append({
                    "student_id": sid, "student": name_by_id[sid], "state": state,
                    "score": latest.score if done else None,
                    "attempt_date": (latest.completed_at or latest.started_at or latest.created_at).isoformat() if (latest.completed_at or latest.started_at or latest.created_at) else None,
                    "attempt_count": len(atts),
                })
            out.append({
                "midterm_id": mid.id, "title": mid.title or f"Midterm #{mid.id}",
                "subject": mid.midterm_subject,
                "assigned": len(student_ids), "started": started, "completed": completed,
                **_agg(completed_scores),
                "students": rows,
            })
        return Response({"midterms": out})


class ClassroomUnifiedResultsView(_ClassroomScopedView):
    """Unified results across assessments, midterms, past papers. Real data only."""

    def get(self, request, classroom_pk):
        classroom = self.get_classroom()
        caps = classroom_capabilities(request.user, classroom)
        if not caps.is_staff:
            return Response({"detail": "Staff only."}, status=http.HTTP_403_FORBIDDEN)

        from exams.models import MockExam, TestAttempt

        f_student = request.query_params.get("student")
        f_type = (request.query_params.get("type") or "all").lower()
        f_from = request.query_params.get("date_from")
        f_to = request.query_params.get("date_to")

        students = _active_students(classroom)
        student_ids = [m.user_id for m in students]
        if f_student:
            try:
                fid = int(f_student)
                student_ids = [i for i in student_ids if i == fid]
            except (TypeError, ValueError):
                pass
        name_by_id = {m.user_id: _display_name(m.user) for m in students}
        rows = []

        # --- Assessments (AssessmentAttempt + AssessmentResult) ---
        if f_type in ("all", "assessment"):
            from assessments.models import AssessmentAttempt
            qs = (AssessmentAttempt.objects
                  .filter(homework__classroom=classroom, student_id__in=student_ids)
                  .select_related("homework__assessment_set", "result"))
            for a in qs:
                res = getattr(a, "result", None)
                rows.append({
                    "student_id": a.student_id, "student": name_by_id.get(a.student_id, str(a.student_id)),
                    "content_name": a.homework.assessment_set.title if a.homework.assessment_set else "Assessment",
                    "type": "Assessment",
                    "score": (float(res.percent) if res is not None else None),
                    "status": a.status,
                    "submission_date": (a.submitted_at or a.started_at).isoformat() if (a.submitted_at or a.started_at) else None,
                })

        # --- Midterms (TestAttempt on MockExam kind=MIDTERM assigned to this classroom) ---
        if f_type in ("all", "midterm"):
            midterm_ids = list(ResourceAccessGrant.objects.filter(
                classroom_id=classroom.pk, scope=ResourceAccessGrant.SCOPE_RESOURCE, resource_type=RT_MIDTERM,
            ).values_list("resource_id", flat=True).distinct())
            titles = {m.id: (m.title or f"Midterm #{m.id}") for m in MockExam.objects.filter(pk__in=midterm_ids)}
            for a in TestAttempt.objects.filter(mock_exam_id__in=midterm_ids, student_id__in=student_ids):
                rows.append({
                    "student_id": a.student_id, "student": name_by_id.get(a.student_id, str(a.student_id)),
                    "content_name": titles.get(a.mock_exam_id, "Midterm"), "type": "Midterm",
                    "score": a.score if a.is_completed else None,
                    "status": "completed" if a.is_completed else "in_progress",
                    "submission_date": (a.completed_at or a.started_at or a.created_at).isoformat() if (a.completed_at or a.started_at or a.created_at) else None,
                })

        # --- Past papers / practice homework (classes.Submission with practice/pastpaper target) ---
        if f_type in ("all", "past paper", "pastpaper", "past_paper"):
            subs = (Submission.objects
                    .filter(assignment__classroom=classroom, student_id__in=student_ids)
                    .exclude(assignment__assessment_homework__isnull=False)
                    .select_related("assignment", "review"))
            for s in subs:
                a = s.assignment
                if not (a.practice_test_id or a.practice_test_ids or a.practice_test_pack_id):
                    continue
                review = getattr(s, "review", None)
                rows.append({
                    "student_id": s.student_id, "student": name_by_id.get(s.student_id, str(s.student_id)),
                    "content_name": a.title, "type": "Past Paper",
                    "score": (float(review.grade) if (review and review.grade is not None) else None),
                    "status": s.status,
                    "submission_date": (s.submitted_at.isoformat() if getattr(s, "submitted_at", None) else (s.created_at.isoformat() if getattr(s, "created_at", None) else None)),
                })

        # Date-range filter (on submission_date).
        def _in_range(r):
            d = r.get("submission_date")
            if f_from and (not d or d < f_from):
                return False
            if f_to and (not d or d > f_to + "T23:59:59"):
                return False
            return True
        if f_from or f_to:
            rows = [r for r in rows if _in_range(r)]

        # Summary cards — only compute what the data supports; null = hide in UI.
        numeric = [r["score"] for r in rows if isinstance(r["score"], (int, float))]
        terminal = [r for r in rows if str(r["status"]).lower() in ("completed", "graded", "reviewed")]
        pending = [r for r in rows if str(r["status"]).lower() in ("in_progress", "submitted", "pending", "needs_revision")]
        summary = {
            "average_score": (round(sum(numeric) / len(numeric), 1) if numeric else None),
            "completion_rate": (round(100.0 * len(terminal) / len(rows), 1) if rows else None),
            "total_attempts": len(rows),
            "pending_work": len(pending),
        }
        rows.sort(key=lambda r: (r.get("submission_date") or ""), reverse=True)
        return Response({"summary": summary, "rows": rows})
