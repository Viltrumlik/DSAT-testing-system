"""Classroom analytics — computed live from source tables + RankingSnapshot.

Hard rule (BUSINESS-ARCHITECTURE §5): every value is a count, mean, ratio, or
historical series of recorded rows. No predictions, risk scores, health/learning
indices, estimated scores, or synthetic metrics. No persisted cache.
"""

from __future__ import annotations

from collections import defaultdict

from . import attendance as attendance_service
from .models import Assignment, ClassroomMembership, Submission, SubmissionReview
from .models_ranking import RankingSnapshot

_COMPLETED_SUB = (Submission.STATUS_SUBMITTED, Submission.STATUS_REVIEWED)


# ── shared helpers ────────────────────────────────────────────────────────────

def _student_ids(classroom) -> list[int]:
    return list(
        classroom.memberships.filter(
            role=ClassroomMembership.ROLE_STUDENT, status=ClassroomMembership.STATUS_ACTIVE
        ).values_list("user_id", flat=True)
    )


def _ordered_periods(classroom, kind) -> list[str]:
    """Distinct period_keys for a kind, newest first (by computed_at)."""
    seen, out = set(), []
    for pk in (
        RankingSnapshot.objects.filter(classroom=classroom, kind=kind)
        .order_by("-computed_at")
        .values_list("period_key", flat=True)
    ):
        if pk not in seen:
            seen.add(pk)
            out.append(pk)
    return out


def _latest_snaps(classroom, kind):
    periods = _ordered_periods(classroom, kind)
    if not periods:
        return []
    return list(
        RankingSnapshot.objects.filter(classroom=classroom, kind=kind, period_key=periods[0]).order_by("rank")
    )


def _bucketize(scores: list[float], n: int = 5) -> list[dict]:
    if not scores:
        return []
    lo, hi = min(scores), max(scores)
    if lo == hi:
        return [{"range": f"{round(lo)}", "count": len(scores)}]
    width = (hi - lo) / n
    buckets = [0] * n
    for s in scores:
        idx = min(n - 1, int((s - lo) / width))
        buckets[idx] += 1
    return [
        {"range": f"{round(lo + i * width)}–{round(lo + (i + 1) * width)}", "count": c}
        for i, c in enumerate(buckets)
    ]


def _academic_assignments(classroom):
    """Non-DRAFT academic assignments (PUBLISHED + ARCHIVED) — grades/history source."""
    return list(
        classroom.assignments.filter(category__in=Assignment.ACADEMIC_CATEGORIES)
        .exclude(status=Assignment.STATUS_DRAFT)
    )


def _completion_map(classroom, student_ids, assignments):
    """Return {student_id: set(completed_assignment_ids)} from real submissions/results."""
    completed: dict[int, set[int]] = defaultdict(set)
    asg_ids = [a.id for a in assignments]
    for student_id, assignment_id, status in Submission.objects.filter(
        assignment_id__in=asg_ids, student_id__in=student_ids
    ).values_list("student_id", "assignment_id", "status"):
        if status in _COMPLETED_SUB:
            completed[student_id].add(assignment_id)
    try:
        from assessments.models import AssessmentResult

        for student_id, assignment_id in (
            AssessmentResult.objects.filter(
                attempt__homework__classroom=classroom, attempt__student_id__in=student_ids
            ).values_list("attempt__student_id", "attempt__homework__assignment_id")
        ):
            if assignment_id in set(asg_ids):
                completed[student_id].add(assignment_id)
    except Exception:
        pass
    return completed


# ── SAT topic (Reading/Writing/Math) accuracy from real per-question correctness ──

def sat_topic_accuracy(classroom, student_ids=None) -> list[dict]:
    """Accuracy by Question.question_type over completed SAT attempts. Real correctness
    (Question.check_answer on recorded answers). The only topic granularity that exists."""
    from exams.models import Question, TestAttempt

    ids = student_ids if student_ids is not None else _student_ids(classroom)
    if not ids:
        return []
    attempts = TestAttempt.objects.filter(student_id__in=ids, current_state="COMPLETED").only("module_answers")

    answers: list[tuple[int, str]] = []  # (question_id, answer)
    qids: set[int] = set()
    for a in attempts:
        ma = a.module_answers or {}
        for _mod, qmap in ma.items():
            if not isinstance(qmap, dict):
                continue
            for qid, ans in qmap.items():
                try:
                    qi = int(qid)
                except (TypeError, ValueError):
                    continue
                qids.add(qi)
                answers.append((qi, ans))
    if not qids:
        return []

    questions = {q.id: q for q in Question.objects.filter(id__in=qids)}
    by_type = defaultdict(lambda: [0, 0])  # type -> [correct, total]
    for qid, ans in answers:
        q = questions.get(qid)
        if q is None:
            continue
        stats = by_type[q.question_type]
        stats[1] += 1
        if ans not in (None, "") and q.check_answer(ans):
            stats[0] += 1

    label = {"READING": "Reading", "WRITING": "Writing", "MATH": "Math"}
    out = [
        {"topic": label.get(t, t), "accuracy": round(100.0 * c / tot, 1), "answered": tot}
        for t, (c, tot) in by_type.items() if tot > 0
    ]
    out.sort(key=lambda r: r["accuracy"], reverse=True)
    return out


# ── student analytics ─────────────────────────────────────────────────────────

def _snap_series(classroom, kind, student_id) -> list[dict]:
    return [
        {
            "period_key": r["period_key"],
            "score": float(r["score"]),
            "rank": r["rank"],
            "computed_at": r["computed_at"].isoformat(),
        }
        for r in RankingSnapshot.objects.filter(classroom=classroom, kind=kind, student_id=student_id)
        .order_by("computed_at")
        .values("period_key", "score", "rank", "computed_at")
    ]


def student_analytics(classroom, student) -> dict:
    sid = student.id
    sat_series = _snap_series(classroom, RankingSnapshot.KIND_SAT, sid)
    academic_series = _snap_series(classroom, RankingSnapshot.KIND_ACADEMIC, sid)

    # Best/Latest SAT from the most recent SAT snapshot's recorded components.
    best = latest = None
    if sat_series:
        comp = (
            RankingSnapshot.objects.filter(classroom=classroom, kind=RankingSnapshot.KIND_SAT, student_id=sid)
            .order_by("-computed_at").values_list("components", flat=True).first()
        ) or {}
        best = comp.get("best")
        latest = comp.get("latest")

    attendance = attendance_service.student_detail(classroom, student)

    # Completion + per-assignment history from real submissions/grades.
    acads = _academic_assignments(classroom)
    completed = _completion_map(classroom, [sid], acads).get(sid, set())
    reviews = {
        r.submission.assignment_id: r
        for r in SubmissionReview.objects.filter(
            submission__assignment__in=acads, submission__student_id=sid
        ).select_related("submission")
    }
    history = []
    # Completion is measured against PUBLISHED work only (archived work is retired).
    published_ids = {a.id for a in acads if a.status == Assignment.STATUS_PUBLISHED}
    for a in acads:
        is_completed = a.id in completed
        review = reviews.get(a.id)
        history.append({
            "assignment_id": a.id, "title": a.title, "category": a.category,
            "completed": is_completed,
            "grade": float(review.grade) if (review and review.grade is not None) else None,
            "max_score": float(a.max_score) if a.max_score is not None else None,
        })
    completed_published = len(completed & published_ids)
    completion_rate = round(100.0 * completed_published / len(published_ids), 1) if published_ids else None

    # Recent performance: last graded items (real grades).
    recent_grades = sorted(
        [h for h in history if h["grade"] is not None],
        key=lambda h: h["assignment_id"], reverse=True,
    )[:5]

    return {
        "sat_score_trend": sat_series,
        "academic_score_trend": academic_series,
        "ranking_history": {
            "sat": [{"period_key": p["period_key"], "rank": p["rank"]} for p in sat_series],
            "academic": [{"period_key": p["period_key"], "rank": p["rank"]} for p in academic_series],
        },
        "attendance_rate": attendance["attendance_score"],
        "attendance_trend": attendance["trend"],
        "completion_rate": completion_rate,
        "best_sat_score": best,
        "latest_sat_score": latest,
        "recent_performance": recent_grades,
        "assignment_completion_history": history,
    }


# ── class analytics ───────────────────────────────────────────────────────────

def _avg(scores: list[float]):
    return round(sum(scores) / len(scores), 1) if scores else None


def class_analytics(classroom) -> dict:
    ids = _student_ids(classroom)
    n_students = len(ids)

    sat_latest = _latest_snaps(classroom, RankingSnapshot.KIND_SAT)
    academic_latest = _latest_snaps(classroom, RankingSnapshot.KIND_ACADEMIC)
    sat_scores = [float(s.score) for s in sat_latest]
    academic_scores = [float(s.score) for s in academic_latest]

    # Improvement trends from real snapshot history (latest period vs previous period).
    def improvement(kind, latest_snaps):
        periods = _ordered_periods(classroom, kind)
        trend_counts = {"IMPROVING": 0, "STABLE": 0, "DECLINING": 0}
        for s in latest_snaps:
            if s.trend:
                trend_counts[s.trend] = trend_counts.get(s.trend, 0) + 1
        avg_delta = None
        if len(periods) >= 2:
            prev = {
                r["student_id"]: float(r["score"])
                for r in RankingSnapshot.objects.filter(classroom=classroom, kind=kind, period_key=periods[1])
                .values("student_id", "score")
            }
            cur_avg = _avg([float(s.score) for s in latest_snaps])
            prev_avg = _avg(list(prev.values()))
            if cur_avg is not None and prev_avg is not None:
                avg_delta = round(cur_avg - prev_avg, 1)
        return {"trend_counts": trend_counts, "avg_delta": avg_delta}

    # Completion + submission rates from real submissions — PUBLISHED work only.
    acads = [a for a in _academic_assignments(classroom) if a.status == Assignment.STATUS_PUBLISHED]
    completed = _completion_map(classroom, ids, acads)
    completion_rates = []
    total_expected = total_done = 0
    for a in acads:
        done = sum(1 for sid in ids if a.id in completed.get(sid, set()))
        completion_rates.append({"assignment_id": a.id, "title": a.title, "completed": done, "students": n_students,
                                 "rate": round(100.0 * done / n_students, 1) if n_students else None})
        total_expected += n_students
        total_done += done
    submission_rate = round(100.0 * total_done / total_expected, 1) if total_expected else None

    return {
        "students": n_students,
        "avg_sat_score": _avg(sat_scores),
        "avg_academic_score": _avg(academic_scores),
        "sat_score_distribution": _bucketize(sat_scores),
        "academic_score_distribution": _bucketize(academic_scores),
        "ranking_distribution": {
            "sat": improvement(RankingSnapshot.KIND_SAT, sat_latest)["trend_counts"],
            "academic": improvement(RankingSnapshot.KIND_ACADEMIC, academic_latest)["trend_counts"],
        },
        "improvement_trends": {
            "sat": improvement(RankingSnapshot.KIND_SAT, sat_latest),
            "academic": improvement(RankingSnapshot.KIND_ACADEMIC, academic_latest),
        },
        "assignment_completion_rates": completion_rates,
        "submission_rate": submission_rate,
        "attendance": attendance_service.class_summary(classroom),
        "topics": sat_topic_accuracy(classroom, ids),
    }
