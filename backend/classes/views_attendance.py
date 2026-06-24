"""Attendance API (inside the classes app — no separate application).

Reads:
  GET  /api/classes/<pk>/attendance/sessions/            staff: list sessions
  GET  /api/classes/<pk>/attendance/sessions/<id>/       staff: roster + marks
  GET  /api/classes/<pk>/attendance/me/                  member: own history + %
  GET  /api/classes/<pk>/attendance/students/<sid>/      staff or self: student detail
  GET  /api/classes/<pk>/attendance/summary/             staff: class rates + trend series
Writes (CanTakeAttendance):
  POST /api/classes/<pk>/attendance/sessions/            create session
  POST /api/classes/<pk>/attendance/sessions/<id>/mark/  bulk upsert (also single quick-correction)
  POST /api/classes/<pk>/attendance/sessions/<id>/mark-all-present/
  POST /api/classes/<pk>/attendance/sessions/<id>/finalize/
"""

from __future__ import annotations

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_date
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from . import attendance as attendance_service
from .capabilities import classroom_capabilities
from .models import ClassroomMembership
from .models_attendance import AttendanceRecord, AttendanceSession
from .permissions import CanTakeAttendance
from .views_rankings import _ClassroomScopedView, _display_name

_VALID_STATUS = {c for c, _ in AttendanceRecord.STATUS_CHOICES}


def _active_students(classroom):
    return (
        classroom.memberships.filter(
            role=ClassroomMembership.ROLE_STUDENT, status=ClassroomMembership.STATUS_ACTIVE
        ).select_related("user")
    )


def _session_brief(s: AttendanceSession, counts: dict | None = None) -> dict:
    return {
        "id": s.id, "date": s.date.isoformat(), "title": s.title,
        "lesson_index": s.lesson_index, "status": s.status,
        "counts": counts,
    }


class AttendanceSessionsView(_ClassroomScopedView):
    """GET list (staff) / POST create (staff)."""

    def get(self, request, classroom_pk):
        classroom = self.get_classroom()
        if not classroom_capabilities(request.user, classroom).can_take_attendance:
            return Response({"detail": "Staff only."}, status=status.HTTP_403_FORBIDDEN)
        sessions = AttendanceSession.objects.filter(classroom=classroom).order_by("-date", "-id")
        return Response({"sessions": [_session_brief(s) for s in sessions]})

    def post(self, request, classroom_pk):
        classroom = self.get_classroom()
        if not classroom_capabilities(request.user, classroom).can_take_attendance:
            return Response({"detail": "Staff only."}, status=status.HTTP_403_FORBIDDEN)
        parsed_date = parse_date(request.data.get("date") or "")
        if parsed_date is None:
            return Response({"detail": "A valid date is required (YYYY-MM-DD)."}, status=400)
        s = AttendanceSession.objects.create(
            classroom=classroom, date=parsed_date,
            title=(request.data.get("title") or "").strip(),
            lesson_index=request.data.get("lesson_index") or None,
            created_by=request.user,
        )
        return Response(_session_brief(s), status=status.HTTP_201_CREATED)


class AttendanceSessionDetailView(_ClassroomScopedView):
    permission_classes = [IsAuthenticated, CanTakeAttendance]

    def _get_session(self, classroom):
        return get_object_or_404(AttendanceSession, pk=self.kwargs["session_id"], classroom=classroom)

    def get(self, request, classroom_pk, session_id):
        classroom = self.get_classroom()
        session = self._get_session(classroom)
        records = {r.student_id: r for r in session.records.all()}
        roster = []
        for m in _active_students(classroom):
            r = records.get(m.user_id)
            roster.append({
                "student_id": m.user_id,
                "name": _display_name(m.user),
                "status": r.status if r else None,
                "note": r.note if r else "",
            })
        return Response({**_session_brief(session), "roster": roster})


class AttendanceMarkView(_ClassroomScopedView):
    """Bulk upsert of records (also serves single quick-corrections)."""

    permission_classes = [IsAuthenticated, CanTakeAttendance]

    @transaction.atomic
    def post(self, request, classroom_pk, session_id):
        classroom = self.get_classroom()
        session = get_object_or_404(AttendanceSession, pk=session_id, classroom=classroom)
        if session.status == AttendanceSession.STATUS_FINALIZED and not classroom_capabilities(
            request.user, classroom
        ).is_owner:
            return Response({"detail": "Session is finalized; only an owner/admin can edit."}, status=403)

        entries = request.data.get("records") or []
        allowed = set(_active_students(classroom).values_list("user_id", flat=True))
        updated = 0
        for e in entries:
            sid = e.get("student_id")
            st = e.get("status")
            if sid not in allowed or st not in _VALID_STATUS:
                continue
            AttendanceRecord.objects.update_or_create(
                session=session, student_id=sid,
                defaults={"status": st, "note": (e.get("note") or "").strip(), "marked_by": request.user},
            )
            updated += 1
        return Response({"status": "marked", "updated": updated})


class AttendanceMarkAllPresentView(_ClassroomScopedView):
    permission_classes = [IsAuthenticated, CanTakeAttendance]

    @transaction.atomic
    def post(self, request, classroom_pk, session_id):
        classroom = self.get_classroom()
        session = get_object_or_404(AttendanceSession, pk=session_id, classroom=classroom)
        existing = {r.student_id: r.status for r in session.records.all()}
        updated = 0
        for m in _active_students(classroom):
            # Preserve an existing EXCUSED mark; set everyone else to PRESENT.
            if existing.get(m.user_id) == AttendanceRecord.STATUS_EXCUSED:
                continue
            AttendanceRecord.objects.update_or_create(
                session=session, student_id=m.user_id,
                defaults={"status": AttendanceRecord.STATUS_PRESENT, "marked_by": request.user},
            )
            updated += 1
        return Response({"status": "all_present", "updated": updated})


class AttendanceFinalizeView(_ClassroomScopedView):
    permission_classes = [IsAuthenticated, CanTakeAttendance]

    def post(self, request, classroom_pk, session_id):
        classroom = self.get_classroom()
        session = get_object_or_404(AttendanceSession, pk=session_id, classroom=classroom)
        session.status = AttendanceSession.STATUS_FINALIZED
        session.save(update_fields=["status", "updated_at"])
        return Response(_session_brief(session))


class AttendanceSummaryView(_ClassroomScopedView):
    def get(self, request, classroom_pk):
        classroom = self.get_classroom()
        if not classroom_capabilities(request.user, classroom).can_take_attendance:
            return Response({"detail": "Staff only."}, status=status.HTTP_403_FORBIDDEN)
        return Response(attendance_service.class_summary(classroom))


class AttendanceMeView(_ClassroomScopedView):
    def get(self, request, classroom_pk):
        classroom = self.get_classroom()  # IsClassMemberCap enforces membership
        return Response(attendance_service.student_detail(classroom, request.user))


class AttendanceStudentView(_ClassroomScopedView):
    def get(self, request, classroom_pk, student_id):
        classroom = self.get_classroom()
        caps = classroom_capabilities(request.user, classroom)
        if not caps.can_take_attendance and request.user.id != int(student_id):
            return Response({"detail": "Forbidden."}, status=status.HTTP_403_FORBIDDEN)
        student = get_object_or_404(
            ClassroomMembership, classroom=classroom, user_id=student_id
        ).user
        return Response(attendance_service.student_detail(classroom, student))
