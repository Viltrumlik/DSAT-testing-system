from __future__ import annotations

import datetime as pydt

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Exists, F, Min, OuterRef, Prefetch, Q
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from users.permissions import IsAuthenticatedAndNotFrozen

from .models import ReviewLog, UserWordProgress, Word, WordDefinition
from .scheduling import ScheduleUpdate, apply_spaced_repetition
from .vocab_serializers import (
    UserWordProgressBriefSerializer,
    UserWordProgressDetailSerializer,
    VocabReviewRequestSerializer,
    WordSerializer,
)


def _word_prefetch():
    return Prefetch(
        "word__definitions",
        queryset=WordDefinition.objects.order_by("order", "id"),
    )


def _local_next_midnight_boundary(now):
    """Timezone-aware start of the calendar day after ``now`` (local to TIME_ZONE)."""
    local = timezone.localtime(now)
    nxt = local.date() + pydt.timedelta(days=1)
    return timezone.make_aware(
        pydt.datetime.combine(nxt, pydt.time.min),
        timezone.get_current_timezone(),
    )


def _local_calendar_day_bounds(now):
    """Inclusive start and exclusive end of the local calendar day containing ``now``."""
    tz = timezone.get_current_timezone()
    local = timezone.localtime(now)
    day_start = timezone.make_aware(
        pydt.datetime.combine(local.date(), pydt.time.min),
        tz,
    )
    day_end = _local_next_midnight_boundary(now)
    return day_start, day_end


def _reviews_logged_for_daily_cap(*, user, day_start, day_end) -> int:
    """
    Count ``ReviewLog`` rows in this local window, excluding the global-first ``again``
    tap on each word — that attempt does not count toward the daily review budget.
    """
    first_log_id_by_word = dict(
        ReviewLog.objects.filter(user=user)
        .values("word_id")
        .annotate(m=Min("id"))
        .values_list("word_id", "m")
    )
    n = 0
    for row in ReviewLog.objects.filter(
        user=user,
        created_at__gte=day_start,
        created_at__lt=day_end,
    ).values("id", "word_id", "result"):
        if row["result"] == ReviewLog.RESULT_AGAIN and first_log_id_by_word.get(row["word_id"]) == row["id"]:
            continue
        n += 1
    return n


def _vocab_usage_today(*, user, day_start, day_end):
    """
    Per-user consumption for the local vocabulary day (enforces caps across requests).

    - ``reviews_logged``: POST /review submissions in the window minus first-ever
      ``again`` per word (those taps do not use a daily review slot).
    - ``new_words_introduced``: progress rows whose ``introduced_at`` falls in this
      local day; ``introduced_at`` is written only after a ``good``/``easy`` outcome
      (including the first graded pass after a prior ``again``/``hard``).
    """
    reviews_logged = _reviews_logged_for_daily_cap(user=user, day_start=day_start, day_end=day_end)
    new_introduced = UserWordProgress.objects.filter(
        user=user,
        introduced_at__gte=day_start,
        introduced_at__lt=day_end,
    ).count()
    return reviews_logged, new_introduced


def _successful_introduction_result(result: str) -> bool:
    """``good`` / ``easy`` are treated as genuinely learning a new word (quota + ``introduced_at``)."""
    r = (result or "").strip().lower()
    return r in (ReviewLog.RESULT_GOOD, ReviewLog.RESULT_EASY)


def _budget_int(raw, *, default: int, ceiling: int, floor: int = 0) -> int:
    """Parse query param; clamp to [floor, ceiling]. Empty/invalid → ``min(default, ceiling)``."""
    if raw is None or raw == "":
        return max(floor, min(ceiling, default))
    try:
        v = int(raw)
    except (TypeError, ValueError):
        return max(floor, min(ceiling, default))
    return max(floor, min(ceiling, v))


def _today_payload_item(progress: UserWordProgress) -> dict:
    return {"progress": UserWordProgressBriefSerializer(progress).data, "word": WordSerializer(progress.word).data}


class VocabTodayView(APIView):
    """
    GET /api/vocab/today/

    Response: ``{ review: [...due progress cards], new: [...words without progress] }``

    Ordering in ``review``: overdue (`next_review_at` null or `< now`),
    then due today (`now ≤ next_review_at < local next midnight`).
    Caps: ``settings.VOCAB_MAX_*``; optional ``?max_new`` / ``?max_review`` (cannot exceed caps).
    Remaining slots subtract per-day usage: review tallies exclude first-ever ``again`` per word;
    new tallies count only successful ``good``/``easy`` introductions via ``introduced_at``.
    """

    permission_classes = [IsAuthenticatedAndNotFrozen]

    def get(self, request):
        user = request.user
        now = timezone.now()
        day_start, day_end = _local_calendar_day_bounds(now)
        reviews_logged, new_introduced = _vocab_usage_today(user=user, day_start=day_start, day_end=day_end)

        max_review = _budget_int(
            request.query_params.get("max_review"),
            default=settings.VOCAB_MAX_REVIEW_PER_DAY,
            ceiling=settings.VOCAB_MAX_REVIEW_PER_DAY,
        )
        max_new = _budget_int(
            request.query_params.get("max_new"),
            default=settings.VOCAB_MAX_NEW_PER_DAY,
            ceiling=settings.VOCAB_MAX_NEW_PER_DAY,
        )

        review_remaining = max(0, max_review - reviews_logged)
        new_remaining = max(0, max_new - new_introduced)

        prefetch = _word_prefetch()

        review_items: list[UserWordProgress] = []
        if review_remaining > 0:
            overdue_qs = (
                UserWordProgress.objects.filter(user=user)
                .filter(Q(next_review_at__isnull=True) | Q(next_review_at__lt=now))
                .select_related("word")
                .prefetch_related(prefetch)
            )
            overdue = list(
                overdue_qs.order_by(F("next_review_at").asc(nulls_first=True), "id")[:review_remaining]
            )

            remainder = review_remaining - len(overdue)
            due_today: list[UserWordProgress] = []
            if remainder > 0:
                due_today = list(
                    UserWordProgress.objects.filter(user=user, next_review_at__gte=now, next_review_at__lt=day_end)
                    .select_related("word")
                    .prefetch_related(prefetch)
                    .order_by("next_review_at", "id")[:remainder]
                )
            review_items = overdue + due_today

        new_words: list[Word] = []
        if new_remaining > 0:
            new_words = list(
                Word.objects.filter(~Exists(UserWordProgress.objects.filter(user=user, word_id=OuterRef("pk"))))
                .prefetch_related(
                    Prefetch("definitions", queryset=WordDefinition.objects.order_by("order", "id"))
                )
                .order_by("language", "text", "id")[:new_remaining]
            )

        payload = {
            "review": [_today_payload_item(p) for p in review_items],
            "new": [WordSerializer(w).data for w in new_words],
            "limits": {
                "review_cap_applied": max_review,
                "new_cap_applied": max_new,
                "review_slots_remaining": review_remaining,
                "new_slots_remaining": new_remaining,
                "ceilings": {
                    "max_review_per_day": settings.VOCAB_MAX_REVIEW_PER_DAY,
                    "max_new_per_day": settings.VOCAB_MAX_NEW_PER_DAY,
                },
            },
            "consumption_today": {
                "local_day_start": day_start.isoformat(),
                "reviews_logged": reviews_logged,
                "new_words_introduced": new_introduced,
            },
            "server_time": now.isoformat(),
            "local_day_end": day_end.isoformat(),
        }

        return Response(payload)


_LEARNING_PHASE_MAX_INTERVAL_DAYS = 29


class VocabSRSReviewView(APIView):
    """
    POST /api/vocab/review/
    Body: { word_id, result: again|hard|good|easy }
    """

    permission_classes = [IsAuthenticatedAndNotFrozen]

    @transaction.atomic
    def post(self, request):
        ser = VocabReviewRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        word_id = int(ser.validated_data["word_id"])
        result = str(ser.validated_data["result"])

        word = Word.objects.filter(pk=word_id).first()
        if not word:
            return Response({"detail": "Word not found."}, status=status.HTTP_404_NOT_FOUND)

        now = timezone.now()
        day_start, day_end = _local_calendar_day_bounds(now)
        reviews_logged, new_introduced = _vocab_usage_today(user=request.user, day_start=day_start, day_end=day_end)

        exists_before_lock = UserWordProgress.objects.filter(user=request.user, word_id=word_id).exists()
        counts_toward_review_daily = exists_before_lock or result != ReviewLog.RESULT_AGAIN
        projected_reviews_today = reviews_logged + (1 if counts_toward_review_daily else 0)

        if settings.VOCAB_MAX_REVIEW_PER_DAY <= 0:
            return Response(
                {"detail": "Daily vocabulary reviews are disabled.", "limit": settings.VOCAB_MAX_REVIEW_PER_DAY},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        if projected_reviews_today > settings.VOCAB_MAX_REVIEW_PER_DAY:
            return Response(
                {"detail": "Daily vocabulary review limit reached.", "limit": settings.VOCAB_MAX_REVIEW_PER_DAY},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        if not exists_before_lock and _successful_introduction_result(result):
            if settings.VOCAB_MAX_NEW_PER_DAY <= 0:
                return Response(
                    {"detail": "New vocabulary introductions are disabled.", "limit": settings.VOCAB_MAX_NEW_PER_DAY},
                    status=status.HTTP_429_TOO_MANY_REQUESTS,
                )
            if new_introduced >= settings.VOCAB_MAX_NEW_PER_DAY:
                return Response(
                    {"detail": "Daily new vocabulary limit reached.", "limit": settings.VOCAB_MAX_NEW_PER_DAY},
                    status=status.HTTP_429_TOO_MANY_REQUESTS,
                )

        created = False
        try:
            progress = UserWordProgress.objects.select_for_update().get(user=request.user, word_id=word_id)
        except UserWordProgress.DoesNotExist:
            try:
                progress = UserWordProgress.objects.create(
                    user=request.user,
                    word=word,
                    ease_factor=2.5,
                    interval=0,
                    repetitions=0,
                    next_review_at=None,
                    introduced_at=None,
                    learning_phase=True,
                )
                progress = UserWordProgress.objects.select_for_update().get(pk=progress.pk)
                created = True
            except IntegrityError:
                progress = UserWordProgress.objects.select_for_update().get(user=request.user, word_id=word_id)

        reviewed_at = now
        upd = apply_spaced_repetition(
            ease_factor=progress.ease_factor,
            interval_days=progress.interval,
            repetitions=progress.repetitions,
            result=result,
            reviewed_at=reviewed_at,
        )

        if created and _successful_introduction_result(result):
            upd = ScheduleUpdate(
                ease_factor=upd.ease_factor,
                interval_days=1,
                repetitions=1,
                next_review_at=reviewed_at + pydt.timedelta(days=1),
            )

        if progress.introduced_at is None and _successful_introduction_result(result):
            introduced_at = reviewed_at
        else:
            introduced_at = progress.introduced_at
        learning_phase = upd.interval_days <= _LEARNING_PHASE_MAX_INTERVAL_DAYS

        progress.ease_factor = upd.ease_factor
        progress.interval = upd.interval_days
        progress.repetitions = upd.repetitions
        progress.next_review_at = upd.next_review_at
        progress.introduced_at = introduced_at
        progress.learning_phase = learning_phase
        progress.save(
            update_fields=[
                "ease_factor",
                "interval",
                "repetitions",
                "next_review_at",
                "introduced_at",
                "learning_phase",
                "updated_at",
            ]
        )

        ReviewLog.objects.create(user=request.user, word=word, result=result)

        progress = (
            UserWordProgress.objects.filter(pk=progress.pk)
            .select_related("word")
            .prefetch_related(_word_prefetch())
            .first()
        )

        return Response({"progress": UserWordProgressDetailSerializer(progress).data}, status=status.HTTP_200_OK)


class VocabAllProgressView(APIView):
    """
    GET /api/vocab/all/
    User progress rows with nested word + definitions.
    """

    permission_classes = [IsAuthenticatedAndNotFrozen]

    def get(self, request):
        user = request.user
        try:
            raw_limit = int(request.query_params.get("limit", "500"))
        except (TypeError, ValueError):
            raw_limit = 500
        limit = max(1, min(2000, raw_limit))

        qs = (
            UserWordProgress.objects.filter(user=user)
            .select_related("word")
            .prefetch_related(_word_prefetch())
            .order_by("-updated_at", "-id")[:limit]
        )
        rows = list(qs)
        return Response(
            {
                "count": len(rows),
                "progress": UserWordProgressDetailSerializer(rows, many=True).data,
            }
        )
