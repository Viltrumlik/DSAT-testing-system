"""Ranking orchestration — gather inputs, compute, rank, persist snapshots.

SAT reads only TestAttempt (SAT). Academic reads only graded SubmissionReview /
AssessmentResult (+ optional attendance). The two never share inputs (BUSINESS-ARCHITECTURE
§3 invariant). Pure math lives in sat.py / academic.py; this module does the DB work.

Snapshots are the history ledger: each recompute upserts a row per (classroom, kind,
period_key, student). `previous_rank` comes from the latest snapshot of a *different*
period, so rank_change/trend are well-defined. Current rankings are computed live here;
no read-cache is persisted (no proven perf need — see §5).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from django.db import transaction
from django.utils import timezone

from exams.models import MockExam, TestAttempt

from ..models import Assignment, ClassroomMembership, Submission
from ..models_ranking import AcademicWeightConfig, RankingSnapshot
from . import academic as academic_math
from . import sat as sat_math
from .sat import Event

SECTION_MIN, SECTION_MAX = 200.0, 800.0
COMPOSITE_MIN, COMPOSITE_MAX = 400.0, 1600.0
ACADEMIC_TREND_EPS = 1.0  # academic points between snapshots for IMPROVING/DECLINING


# ── eligibility helpers ───────────────────────────────────────────────────────

def _attempt_is_sat_scaled(attempt: TestAttempt) -> bool:
    pt = attempt.practice_test
    if pt is None:
        return False
    if attempt.mock_exam_id or pt.mock_exam_id:
        mock = attempt.mock_exam or pt.mock_exam
        if mock is None:
            return False
        if mock.kind == MockExam.KIND_MIDTERM:
            return getattr(mock, "midterm_scoring_scale", None) == MockExam.SCALE_800
        return mock.kind == MockExam.KIND_MOCK_SAT
    # Any non-mock section (standalone pastpaper or practice-test pack) is a
    # SAT-scaled section score.
    return pt.mock_exam_id is None


def _parent_key(attempt: TestAttempt):
    pt = attempt.practice_test
    if attempt.mock_exam_id or pt.mock_exam_id:
        return ("mock", attempt.mock_exam_id or pt.mock_exam_id)
    if pt.practice_test_pack_id:
        return ("ptp", pt.practice_test_pack_id)
    # Standalone pastpaper section: it is its own parent.
    return ("pt", pt.id)


def _classroom_sat_mode(classroom):
    """Return (subject_filter, lo, hi, composite?) for the class subject.

    Subject-specific classes rank by the matching section (200–800). A future BOTH
    subject would rank by the 400–1600 composite (composite=True).
    """
    subj = str(getattr(classroom, "subject", "") or "").upper()
    if subj == "MATH":
        return ("MATH", SECTION_MIN, SECTION_MAX, False)
    if subj in ("ENGLISH", "READING_WRITING"):
        return ("READING_WRITING", SECTION_MIN, SECTION_MAX, False)
    # BOTH (not yet a stored choice) → full composite
    return (None, COMPOSITE_MIN, COMPOSITE_MAX, True)


def _build_sat_events(student_ids: list[int], classroom) -> dict[int, list[Event]]:
    """Per-student eligible SAT events (section score, or composite for BOTH classes)."""
    subject_filter, lo, hi, composite = _classroom_sat_mode(classroom)

    qs = (
        TestAttempt.objects.filter(
            student_id__in=student_ids,
            current_state="COMPLETED",
            score__isnull=False,
        )
        .select_related("practice_test", "practice_test__mock_exam", "mock_exam")
    )

    # best score per (student, parent, subject)
    best: dict[tuple, tuple[float, datetime]] = {}
    for a in qs:
        if not _attempt_is_sat_scaled(a):
            continue
        subj = a.practice_test.subject
        if not composite and subj != subject_filter:
            continue
        score = max(SECTION_MIN, min(SECTION_MAX, float(a.score)))
        when = a.completed_at or a.submitted_at
        if when is None:
            continue
        k = (a.student_id, _parent_key(a), subj)
        cur = best.get(k)
        if cur is None or score > cur[0]:
            best[k] = (score, when)

    events: dict[int, list[Event]] = defaultdict(list)
    if not composite:
        for (student_id, _parent, _subj), (score, when) in best.items():
            events[student_id].append(Event(score=score, completed_at=when))
        return events

    # composite: pair R&W + Math under the same parent
    by_parent: dict[tuple, dict[str, tuple[float, datetime]]] = defaultdict(dict)
    for (student_id, parent, subj), val in best.items():
        by_parent[(student_id, parent)][subj] = val
    for (student_id, _parent), sections in by_parent.items():
        rw = sections.get("READING_WRITING")
        ma = sections.get("MATH")
        if rw and ma:
            events[student_id].append(
                Event(score=rw[0] + ma[0], completed_at=max(rw[1], ma[1]))
            )
    return events


# ── academic gathering ────────────────────────────────────────────────────────

def _build_academic_inputs(student_ids: list[int], classroom, now):
    """Return per-student (category_percents, completion_ratio, missing/late counts)."""
    # Grades count from PUBLISHED + ARCHIVED (archived keeps earned grades); DRAFT counts nowhere.
    academic_assignments = list(
        classroom.assignments.filter(category__in=Assignment.ACADEMIC_CATEGORIES)
        .exclude(status=Assignment.STATUS_DRAFT)
    )
    assignment_by_id = {a.id: a for a in academic_assignments}
    # "Assigned" (completion denominator) = PUBLISHED work currently expected (no due date,
    # or past due). ARCHIVED work leaves the denominator so retiring work isn't punitive.
    assigned_ids = {
        a.id
        for a in academic_assignments
        if a.status == Assignment.STATUS_PUBLISHED and (a.due_at is None or a.due_at <= now)
    }

    cat_percents: dict[int, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    completed: dict[int, set[int]] = defaultdict(set)
    late: dict[int, int] = defaultdict(int)
    assessment_graded_assignment_ids: set[int] = set()

    # Assessment results (auto-graded quizzes/homework linked to a classes.Assignment).
    try:
        from assessments.models import AssessmentResult

        ar_qs = (
            AssessmentResult.objects.filter(
                attempt__homework__classroom=classroom,
                attempt__student_id__in=student_ids,
            )
            .select_related("attempt", "attempt__homework", "attempt__homework__assignment")
        )
        for r in ar_qs:
            att = r.attempt
            hw = att.homework
            asg = getattr(hw, "assignment", None)
            category = (
                asg.category
                if asg and asg.category in Assignment.ACADEMIC_CATEGORIES
                else Assignment.CATEGORY_QUIZ
            )
            cat_percents[att.student_id][category].append(float(r.percent))
            if asg is not None:
                assessment_graded_assignment_ids.add(asg.id)
                completed[att.student_id].add(asg.id)
    except Exception:  # assessments app optional / linkage absent
        pass

    # Teacher-graded submissions (skip assignments already covered by assessment results).
    sub_qs = (
        Submission.objects.filter(
            assignment__in=academic_assignments, student_id__in=student_ids
        )
        .select_related("review", "assignment")
    )
    for s in sub_qs:
        asg = s.assignment
        if s.status in (Submission.STATUS_SUBMITTED, Submission.STATUS_REVIEWED):
            completed[s.student_id].add(asg.id)
            if asg.due_at and s.submitted_at and s.submitted_at > asg.due_at:
                late[s.student_id] += 1
        if asg.id in assessment_graded_assignment_ids:
            continue
        review = getattr(s, "review", None)
        if review is not None:
            pct = review.normalized_percent()
            if pct is not None:
                cat_percents[s.student_id][asg.category].append(pct)

    results = {}
    n_assigned = len(assigned_ids)
    for sid in student_ids:
        done = len(completed[sid] & assigned_ids)
        ratio = (done / n_assigned) if n_assigned else 1.0
        results[sid] = {
            "category_percents": {k: v for k, v in cat_percents[sid].items()},
            "completion_ratio": ratio,
            "missing_count": max(0, n_assigned - done),
            "late_count": late[sid],
        }
    return results


# ── ranking + persistence ─────────────────────────────────────────────────────

def _student_ids(classroom) -> list[int]:
    return list(
        classroom.memberships.filter(
            role=ClassroomMembership.ROLE_STUDENT, status=ClassroomMembership.STATUS_ACTIVE
        ).values_list("user_id", flat=True)
    )


def _previous_ranks(classroom, kind: str, current_period: str) -> dict[int, int]:
    """Latest rank per student from a snapshot of a *different* period (for rank_change)."""
    rows = (
        RankingSnapshot.objects.filter(classroom=classroom, kind=kind)
        .exclude(period_key=current_period)
        .order_by("student_id", "-computed_at")
        .values("student_id", "rank", "computed_at")
    )
    out: dict[int, int] = {}
    for r in rows:  # first per student wins (ordered by -computed_at)
        out.setdefault(r["student_id"], r["rank"])
    return out


def _percentile(score: float, all_scores: list[float]) -> float:
    n = len(all_scores)
    if n <= 1:
        return 100.0
    below = sum(1 for s in all_scores if s < score)
    equal = sum(1 for s in all_scores if s == score) - 1
    return round(100.0 * (below + 0.5 * equal) / (n - 1), 1)


@transaction.atomic
def recompute_classroom(classroom, *, kinds=("SAT", "ACADEMIC"), period_key=None, now=None) -> dict:
    now = now or timezone.now()
    period_key = period_key or now.date().isoformat()
    student_ids = _student_ids(classroom)
    summary = {}

    if "SAT" in kinds:
        summary["SAT"] = _recompute_sat(classroom, student_ids, period_key, now)
    if "ACADEMIC" in kinds:
        summary["ACADEMIC"] = _recompute_academic(classroom, student_ids, period_key, now)
    return summary


def _recompute_sat(classroom, student_ids, period_key, now) -> int:
    _, lo, hi, _ = _classroom_sat_mode(classroom)
    events_by_student = _build_sat_events(student_ids, classroom)

    computed = []
    for sid in student_ids:
        res = sat_math.compute_sat(events_by_student.get(sid, []), now=now, lo=lo, hi=hi)
        if res is not None:  # unranked students (no SAT events) are excluded
            computed.append((sid, res))

    computed.sort(key=lambda t: (-t[1]["sat_score"], -t[1]["peak_ability"], -t[1]["latest"], t[0]))
    scores = [c[1]["sat_score"] for c in computed]
    prev = _previous_ranks(classroom, RankingSnapshot.KIND_SAT, period_key)

    for rank, (sid, res) in enumerate(computed, start=1):
        prev_rank = prev.get(sid)
        RankingSnapshot.objects.update_or_create(
            classroom=classroom, kind=RankingSnapshot.KIND_SAT, period_key=period_key, student_id=sid,
            defaults=dict(
                rank=rank,
                previous_rank=prev_rank,
                score=res["sat_score"],
                percentile=_percentile(res["sat_score"], scores),
                trend=res["trend"],
                confidence=res["confidence"],
                components={**res, "rank_change": (prev_rank - rank) if prev_rank else None},
                computed_at=now,
            ),
        )
    return len(computed)


def _recompute_academic(classroom, student_ids, period_key, now) -> int:
    weights_cfg, _ = AcademicWeightConfig.objects.get_or_create(classroom=classroom)
    weights = weights_cfg.category_weights()
    missing_as_zero = weights_cfg.missing_as_zero
    inputs = _build_academic_inputs(student_ids, classroom, now)

    # Attendance integration (§4.1): only when the teacher has weighted it > 0.
    if weights.get("ATTENDANCE", 0.0) > 0:
        from ..attendance import attendance_scores_for

        att = attendance_scores_for(classroom, student_ids)
        for sid in student_ids:
            score = att.get(sid)
            if score is not None:  # no counted sessions → category stays inactive for this student
                inputs[sid]["category_percents"]["ATTENDANCE"] = [score]

    computed = []
    for sid in student_ids:
        data = inputs[sid]
        perf, perf_comp = academic_math.performance_score(data["category_percents"], weights)
        # Nothing graded and nothing assigned → unranked (excluded).
        if perf == 0.0 and not data["category_percents"] and data["missing_count"] == 0:
            continue
        scored = academic_math.academic_score(
            perf, data["completion_ratio"], missing_as_zero=missing_as_zero
        )
        components = {
            **scored,
            **perf_comp,
            "missing_count": data["missing_count"],
            "late_count": data["late_count"],
        }
        computed.append((sid, scored["academic_score"], perf, data["completion_ratio"], components))

    computed.sort(key=lambda t: (-t[1], -t[2], -t[3], t[0]))
    scores = [c[1] for c in computed]
    prev = _previous_ranks(classroom, RankingSnapshot.KIND_ACADEMIC, period_key)
    prev_scores = _previous_scores(classroom, RankingSnapshot.KIND_ACADEMIC, period_key)

    for rank, (sid, score, _perf, _ratio, components) in enumerate(computed, start=1):
        prev_rank = prev.get(sid)
        trend = _academic_trend(prev_scores.get(sid), score)
        RankingSnapshot.objects.update_or_create(
            classroom=classroom, kind=RankingSnapshot.KIND_ACADEMIC, period_key=period_key, student_id=sid,
            defaults=dict(
                rank=rank,
                previous_rank=prev_rank,
                score=score,
                percentile=_percentile(score, scores),
                trend=trend,
                confidence=None,
                components={**components, "trend": trend, "rank_change": (prev_rank - rank) if prev_rank else None},
                computed_at=now,
            ),
        )
    return len(computed)


def _previous_scores(classroom, kind, current_period) -> dict[int, float]:
    rows = (
        RankingSnapshot.objects.filter(classroom=classroom, kind=kind)
        .exclude(period_key=current_period)
        .order_by("student_id", "-computed_at")
        .values("student_id", "score", "computed_at")
    )
    out: dict[int, float] = {}
    for r in rows:
        out.setdefault(r["student_id"], float(r["score"]))
    return out


def _academic_trend(prev_score, score) -> str:
    if prev_score is None:
        return RankingSnapshot.TREND_STABLE
    delta = score - prev_score
    if delta > ACADEMIC_TREND_EPS:
        return RankingSnapshot.TREND_IMPROVING
    if delta < -ACADEMIC_TREND_EPS:
        return RankingSnapshot.TREND_DECLINING
    return RankingSnapshot.TREND_STABLE
