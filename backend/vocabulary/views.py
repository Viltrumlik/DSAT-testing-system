from __future__ import annotations

from datetime import timedelta

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from access.permissions import CanManageQuestions

from .models import VocabularyWord, UserVocabularyProgress, UserVocabularyReviewEvent
from .serializers import (
    VocabularyReviewSerializer,
    VocabularyWordSerializer,
    VocabularyWordAdminWriteSerializer,
    UserVocabularyProgressSerializer,
)


def _today_local_date() -> timezone.datetime.date:
    return timezone.localdate()


def _compute_streak_days(*, user_id: int, max_lookback_days: int = 120) -> int:
    """
    Streak = consecutive calendar days ending today where the user has >=1 review event.
    """
    today = _today_local_date()
    start = today - timedelta(days=max_lookback_days)
    qs = (
        UserVocabularyReviewEvent.objects.filter(
            user_id=user_id,
            reviewed_at__date__gte=start,
            reviewed_at__date__lte=today,
        )
        .values_list("reviewed_at__date", flat=True)
        .distinct()
    )
    days = set(qs)
    streak = 0
    d = today
    while d in days:
        streak += 1
        d = d - timedelta(days=1)
    return streak


class VocabularyWordsView(APIView):
    """
    GET /api/vocabulary/words
    - Student: browse words (optionally filtered) for discovery
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        q = (request.query_params.get("q") or "").strip()
        diff = request.query_params.get("difficulty")
        pos = (request.query_params.get("part_of_speech") or "").strip().lower()

        qs = VocabularyWord.objects.all()
        if q:
            qs = qs.filter(Q(word__icontains=q) | Q(meaning__icontains=q))
        if diff:
            try:
                dv = int(diff)
                qs = qs.filter(difficulty=dv)
            except (TypeError, ValueError):
                pass
        if pos:
            qs = qs.filter(part_of_speech=pos)

        qs = qs.order_by("word", "id")[:500]
        return Response(VocabularyWordSerializer(qs, many=True).data)


class VocabularyDailyView(APIView):
    """
    GET /api/vocabulary/daily
    Returns a daily session payload:
    - due reviews first (next_review_at <= now)
    - then new words to reach target size
    Includes stats snapshot (learned, accuracy, streak).
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        now = timezone.now()

        target = request.query_params.get("target")
        try:
            target_n = max(1, min(30, int(target))) if target else 10
        except (TypeError, ValueError):
            target_n = 10

        # Due reviews
        due_progress = list(
            UserVocabularyProgress.objects.filter(
                user=user,
            )
            .filter(Q(next_review_at__isnull=False) & Q(next_review_at__lte=now))
            .exclude(status=UserVocabularyProgress.STATUS_MASTERED)
            .select_related("word")
            .order_by("next_review_at", "id")[:target_n]
        )
        due_word_ids = {p.word_id for p in due_progress}

        remaining = max(0, target_n - len(due_progress))

        # New words not yet seen by the user (exclude any existing progress)
        new_words = []
        if remaining > 0:
            seen_ids = set(
                UserVocabularyProgress.objects.filter(user=user).values_list("word_id", flat=True)
            )
            new_words = list(
                VocabularyWord.objects.exclude(id__in=seen_ids | due_word_ids)
                .order_by("-created_at", "id")[:remaining]
            )

        items = []
        for p in due_progress:
            items.append(
                {
                    "kind": "review",
                    "progress": UserVocabularyProgressSerializer(p).data,
                    "word": VocabularyWordSerializer(p.word).data,
                }
            )
        for w in new_words:
            items.append(
                {
                    "kind": "new",
                    "progress": None,
                    "word": VocabularyWordSerializer(w).data,
                }
            )

        agg = (
            UserVocabularyProgress.objects.filter(user=user).aggregate(
                correct=Sum("correct_count"), wrong=Sum("wrong_count")
            )
            or {}
        )
        correct = int(agg.get("correct") or 0)
        wrong = int(agg.get("wrong") or 0)
        attempts = correct + wrong
        accuracy = (correct / attempts * 100.0) if attempts > 0 else 0.0
        learned = int(
            UserVocabularyProgress.objects.filter(user=user, status=UserVocabularyProgress.STATUS_MASTERED).count()
        )
        streak = _compute_streak_days(user_id=user.pk)

        return Response(
            {
                "target": target_n,
                "items": items,
                "stats": {
                    "total_learned": learned,
                    "accuracy_percent": round(accuracy, 1),
                    "streak_days": streak,
                },
                "server_time": now.isoformat(),
            }
        )


class VocabularyReviewView(APIView):
    """
    POST /api/vocabulary/review
    Payload: { word_id, result: "correct"|"wrong" }
    Updates progress + schedules next review, and records a review event (for streak + analytics).
    """

    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        user = request.user
        s = VocabularyReviewSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        word_id = int(s.validated_data["word_id"])
        result = str(s.validated_data["result"])

        word = VocabularyWord.objects.filter(pk=word_id).first()
        if not word:
            return Response({"detail": "Word not found."}, status=status.HTTP_404_NOT_FOUND)

        progress, _created = UserVocabularyProgress.objects.select_for_update().get_or_create(
            user=user,
            word=word,
            defaults={
                "status": UserVocabularyProgress.STATUS_NEW,
                "correct_count": 0,
                "wrong_count": 0,
            },
        )

        reviewed_at = timezone.now()
        progress.mark_review(result=result, reviewed_at=reviewed_at)
        progress.save()

        UserVocabularyReviewEvent.objects.create(
            user=user,
            word=word,
            result=result,
            reviewed_at=reviewed_at,
        )

        return Response(
            {
                "progress": UserVocabularyProgressSerializer(progress).data,
                "word": VocabularyWordSerializer(word).data,
            },
            status=status.HTTP_200_OK,
        )


class AdminVocabularyWordListCreateView(APIView):
    """
    Admin CRUD for in-app UI (mirrors exams admin style):
    GET /api/vocabulary/admin/words/
    POST /api/vocabulary/admin/words/
    """

    permission_classes = [IsAuthenticated, CanManageQuestions]

    def get(self, request):
        qs = VocabularyWord.objects.all().order_by("-created_at", "-id")[:2000]
        return Response(VocabularyWordSerializer(qs, many=True).data)

    def post(self, request):
        s = VocabularyWordAdminWriteSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        w = s.save()
        return Response(VocabularyWordSerializer(w).data, status=status.HTTP_201_CREATED)


class AdminVocabularyWordDetailView(APIView):
    """
    Admin CRUD for in-app UI:
    PATCH /api/vocabulary/admin/words/<id>/
    DELETE /api/vocabulary/admin/words/<id>/
    """

    permission_classes = [IsAuthenticated, CanManageQuestions]

    def patch(self, request, pk: int):
        w = VocabularyWord.objects.filter(pk=pk).first()
        if not w:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        s = VocabularyWordAdminWriteSerializer(w, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        w = s.save()
        return Response(VocabularyWordSerializer(w).data)

    def delete(self, request, pk: int):
        w = VocabularyWord.objects.filter(pk=pk).first()
        if not w:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        w.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

