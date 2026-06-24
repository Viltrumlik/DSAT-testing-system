"""Teacher gradebook API (staff-only) — operational visibility over analytics.

GET /api/classes/<pk>/gradebook/                      per-assignment status distribution
GET /api/classes/<pk>/gradebook/assignments/<id>/     full roster × status for one assignment

Status taxonomy (operational): MISSING (no submission or still DRAFT), SUBMITTED (manual
work awaiting grading), NEEDS_REVISION (RETURNED), GRADED (REVIEWED — source AUTO or TEACHER).
Auto-graded work is always GRADED with a score and never appears as needs-grading.
"""

from __future__ import annotations

from collections import defaultdict

from django.shortcuts import get_object_or_404
from rest_framework import status as http
from rest_framework.response import Response

from .capabilities import classroom_capabilities
from .models import Assignment, ClassroomMembership, Submission
from .views_rankings import _ClassroomScopedView, _display_name

# Gradebook cell statuses
GB_MISSING = "MISSING"
GB_SUBMITTED = "SUBMITTED"
GB_NEEDS_REVISION = "NEEDS_REVISION"
GB_GRADED = "GRADED"


def _cell(sub: Submission | None) -> dict:
    """Map a submission (or None) to an operational gradebook cell."""
    if sub is None or sub.status == Submission.STATUS_DRAFT:
        return {"status": GB_MISSING, "grade": None, "max_score": None, "source": None, "submission_id": sub.id if sub else None}
    if sub.status == Submission.STATUS_SUBMITTED:
        return {"status": GB_SUBMITTED, "grade": None, "max_score": None, "source": None, "submission_id": sub.id}
    if sub.status == Submission.STATUS_RETURNED:
        return {"status": GB_NEEDS_REVISION, "grade": None, "max_score": None, "source": None, "submission_id": sub.id}
    # REVIEWED
    review = getattr(sub, "review", None)
    grade = str(review.grade) if (review and review.grade is not None) else None
    max_score = str(review.max_score) if (review and review.max_score is not None) else None
    source = ("AUTO" if review.is_auto else "TEACHER") if review else "TEACHER"
    return {"status": GB_GRADED, "grade": grade, "max_score": max_score, "source": source, "submission_id": sub.id}


def _perf_stats(sub_map: dict, total: int) -> dict:
    """Assignment-level score stats for auto-graded work (real recorded grades)."""
    grades = []
    for s in sub_map.values():
        if s.status == Submission.STATUS_REVIEWED:
            r = getattr(s, "review", None)
            if r and r.grade is not None:
                grades.append(float(r.grade))
    if not grades:
        return {"completion_rate": round(0.0, 1), "average": None, "highest": None, "lowest": None, "completed": 0}
    return {
        "completion_rate": round(100.0 * len(grades) / total, 1) if total else None,
        "average": round(sum(grades) / len(grades), 1),
        "highest": max(grades),
        "lowest": min(grades),
        "completed": len(grades),
    }


def _counts(cells: list[dict]) -> dict:
    c = {GB_GRADED: 0, GB_SUBMITTED: 0, GB_NEEDS_REVISION: 0, GB_MISSING: 0}
    for cell in cells:
        c[cell["status"]] = c.get(cell["status"], 0) + 1
    c["total"] = len(cells)
    return c


def _active_student_ids(classroom) -> list[int]:
    return list(
        classroom.memberships.filter(
            role=ClassroomMembership.ROLE_STUDENT, status=ClassroomMembership.STATUS_ACTIVE
        ).values_list("user_id", flat=True)
    )


def _assignment_meta(a: Assignment) -> dict:
    return {
        "id": a.id,
        "title": a.title,
        "status": a.status,
        "category": a.category,
        "due_at": a.due_at,
        "is_auto_graded": a.is_auto_graded,
        "source_label": a.auto_source_label,
        "max_score": str(a.max_score) if a.max_score is not None else None,
    }


class GradebookOverviewView(_ClassroomScopedView):
    """Per-assignment status distribution so a teacher sees class health in seconds."""

    def get(self, request, classroom_pk):
        classroom = self.get_classroom()
        if not classroom_capabilities(request.user, classroom).is_staff:
            return Response({"detail": "Staff only."}, status=http.HTTP_403_FORBIDDEN)

        student_ids = _active_student_ids(classroom)
        assignments = list(
            classroom.assignments.exclude(status=Assignment.STATUS_ARCHIVED).order_by("-created_at")
        )
        # All relevant submissions in one query, grouped by assignment → student.
        subs_by_assignment: dict[int, dict[int, Submission]] = defaultdict(dict)
        for s in (
            Submission.objects.filter(assignment__in=assignments, student_id__in=student_ids)
            .select_related("review")
        ):
            subs_by_assignment[s.assignment_id][s.student_id] = s

        rows = []
        for a in assignments:
            sub_map = subs_by_assignment.get(a.id, {})
            cells = [_cell(sub_map.get(sid)) for sid in student_ids]
            counts = _counts(cells)
            # Auto-graded assignments never surface needs-grading.
            needs_grading = 0 if a.is_auto_graded else counts[GB_SUBMITTED]
            rows.append({
                **_assignment_meta(a),
                "counts": {
                    "graded": counts[GB_GRADED],
                    "needs_grading": needs_grading,
                    "submitted": counts[GB_SUBMITTED],
                    "needs_revision": counts[GB_NEEDS_REVISION],
                    "missing": counts[GB_MISSING],
                    "total": counts["total"],
                },
                "performance": _perf_stats(sub_map, counts["total"]) if a.is_auto_graded else None,
            })

        total_needs_grading = sum(r["counts"]["needs_grading"] for r in rows)
        return Response({"assignments": rows, "needs_grading_total": total_needs_grading, "students": len(student_ids)})


class GradebookAssignmentView(_ClassroomScopedView):
    """Full roster × status for one assignment, with filters answered client-side."""

    def get(self, request, classroom_pk, assignment_id):
        classroom = self.get_classroom()
        if not classroom_capabilities(request.user, classroom).is_staff:
            return Response({"detail": "Staff only."}, status=http.HTTP_403_FORBIDDEN)
        assignment = get_object_or_404(Assignment, pk=assignment_id, classroom=classroom)

        members = list(
            classroom.memberships.filter(
                role=ClassroomMembership.ROLE_STUDENT, status=ClassroomMembership.STATUS_ACTIVE
            ).select_related("user")
        )
        sub_map = {
            s.student_id: s
            for s in Submission.objects.filter(
                assignment=assignment, student_id__in=[m.user_id for m in members]
            ).select_related("review")
        }

        roster = []
        cells = []
        for m in members:
            cell = _cell(sub_map.get(m.user_id))
            cells.append(cell)
            roster.append({
                "student_id": m.user_id,
                "name": _display_name(m.user),
                "email": m.user.email,
                **cell,
            })
        counts = _counts(cells)
        return Response({
            "assignment": _assignment_meta(assignment),
            "roster": roster,
            "counts": {
                "graded": counts[GB_GRADED],
                "needs_grading": 0 if assignment.is_auto_graded else counts[GB_SUBMITTED],
                "submitted": counts[GB_SUBMITTED],
                "needs_revision": counts[GB_NEEDS_REVISION],
                "missing": counts[GB_MISSING],
                "total": counts["total"],
            },
            "performance": _perf_stats(sub_map, counts["total"]) if assignment.is_auto_graded else None,
        })
