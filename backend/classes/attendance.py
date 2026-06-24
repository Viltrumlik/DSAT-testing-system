"""Attendance service — scoring, history, trend, and the batch helper the Academic
ranking integration consumes. Lives inside the classes app (no separate application).

attendance_score = 100 · Σ weight(status) / (counted, non-EXCUSED sessions)
  PRESENT=1.0  LATE=0.5  ABSENT=0.0   EXCUSED excluded from the denominator
"counted" sessions are FINALIZED sessions that have at least one record.
See docs/classroom-rebuild/BUSINESS-ARCHITECTURE.md §4 / §4.1.
"""

from __future__ import annotations

from collections import defaultdict

from .models_attendance import AttendanceRecord, AttendanceSession

_EXCUSED = AttendanceRecord.STATUS_EXCUSED
_WEIGHT = AttendanceRecord.SCORE_WEIGHT  # PRESENT/LATE/ABSENT
TREND_EPS = 0.05  # per-session score slope band for STABLE


def compute_attendance_score(statuses: list[str]) -> float | None:
    """0–100 over countable statuses, or None if the student has no countable sessions."""
    countable = [s for s in statuses if s != _EXCUSED]
    if not countable:
        return None
    total = sum(_WEIGHT.get(s, 0.0) for s in countable)
    return round(100.0 * total / len(countable), 1)


def _finalized_records(classroom, student_ids=None):
    qs = AttendanceRecord.objects.filter(
        session__classroom=classroom, session__status=AttendanceSession.STATUS_FINALIZED
    )
    if student_ids is not None:
        qs = qs.filter(student_id__in=student_ids)
    return qs


def attendance_scores_for(classroom, student_ids: list[int]) -> dict[int, float | None]:
    """Batch attendance_score per student (for ranking). None when no counted sessions."""
    by_student: dict[int, list[str]] = defaultdict(list)
    for student_id, status in _finalized_records(classroom, student_ids).values_list("student_id", "status"):
        by_student[student_id].append(status)
    return {sid: compute_attendance_score(by_student.get(sid, [])) for sid in student_ids}


def _status_value(status: str) -> float | None:
    if status == _EXCUSED:
        return None
    return _WEIGHT.get(status, 0.0)


def _trend(series: list[float]) -> str:
    """IMPROVING/STABLE/DECLINING from least-squares slope of per-session scores (0–1)."""
    m = len(series)
    if m < 2:
        return "STABLE"
    xs = list(range(m))
    mx = sum(xs) / m
    my = sum(series) / m
    denom = sum((x - mx) ** 2 for x in xs)
    if denom == 0:
        return "STABLE"
    slope = sum((xs[i] - mx) * (series[i] - my) for i in range(m)) / denom
    if slope > TREND_EPS:
        return "IMPROVING"
    if slope < -TREND_EPS:
        return "DECLINING"
    return "STABLE"


def student_detail(classroom, student) -> dict:
    """A student's attendance: percentage, counts, chronological history, and trend."""
    records = list(
        AttendanceRecord.objects.filter(session__classroom=classroom, student=student)
        .select_related("session")
        .order_by("session__date", "session__id")
    )
    counts = {AttendanceRecord.STATUS_PRESENT: 0, AttendanceRecord.STATUS_ABSENT: 0,
              AttendanceRecord.STATUS_LATE: 0, _EXCUSED: 0}
    history = []
    finalized_statuses: list[str] = []
    finalized_series: list[float] = []
    for r in records:
        counts[r.status] = counts.get(r.status, 0) + 1
        history.append({
            "session_id": r.session_id,
            "date": r.session.date.isoformat(),
            "title": r.session.title,
            "status": r.status,
            "note": r.note,
            "finalized": r.session.status == AttendanceSession.STATUS_FINALIZED,
        })
        if r.session.status == AttendanceSession.STATUS_FINALIZED:
            finalized_statuses.append(r.status)
            v = _status_value(r.status)
            if v is not None:
                finalized_series.append(v)

    return {
        "attendance_score": compute_attendance_score(finalized_statuses),
        "counted_sessions": sum(1 for s in finalized_statuses if s != _EXCUSED),
        "counts": counts,
        "trend": _trend(finalized_series),
        "history": history,
    }


def class_summary(classroom) -> dict:
    """Class-wide attendance: per-session present-rate series (trend chart) + per-student rates."""
    from .models import ClassroomMembership

    members = list(
        classroom.memberships.filter(
            role=ClassroomMembership.ROLE_STUDENT, status=ClassroomMembership.STATUS_ACTIVE
        ).select_related("user")
    )
    student_ids = [m.user_id for m in members]
    scores = attendance_scores_for(classroom, student_ids)
    name = lambda u: (f"{u.first_name} {u.last_name}".strip() or u.username or u.email)
    students = [
        {"student_id": m.user_id, "name": name(m.user), "attendance_score": scores.get(m.user_id)}
        for m in members
    ]

    sessions = []
    for s in (
        AttendanceSession.objects.filter(
            classroom=classroom, status=AttendanceSession.STATUS_FINALIZED
        ).order_by("date", "id").prefetch_related("records")
    ):
        recs = list(s.records.all())
        countable = [r for r in recs if r.status != _EXCUSED]
        present_rate = (
            round(100.0 * sum(_WEIGHT.get(r.status, 0.0) for r in countable) / len(countable), 1)
            if countable else None
        )
        sessions.append({
            "id": s.id, "date": s.date.isoformat(), "title": s.title,
            "present_rate": present_rate, "records": len(recs),
        })

    rated = [st["attendance_score"] for st in students if st["attendance_score"] is not None]
    overall = round(sum(rated) / len(rated), 1) if rated else None
    return {"overall_rate": overall, "students": students, "sessions": sessions}
