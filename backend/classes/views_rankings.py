"""Ranking API — leaderboard reads (visibility-aware) + manual recompute.

GET  /api/classes/<pk>/rankings/<kind>/   → leaderboard for SAT|ACADEMIC
POST /api/classes/<pk>/rankings/recompute/ → recompute now (managers/admin)

Visibility honors ClassroomRankingConfig (FULL/ANONYMOUS/HIDDEN + hide_score_values),
per BUSINESS-ARCHITECTURE §3.5. Staff/admin always see the full named board with scores.
"""

from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .capabilities import classroom_capabilities
from .models import Classroom
from .models_ranking import ClassroomRankingConfig, RankingSnapshot
from .permissions import CanConfigureRanking, CanRecomputeRanking, IsClassMemberCap
from .ranking import service

_VALID_KINDS = {RankingSnapshot.KIND_SAT, RankingSnapshot.KIND_ACADEMIC}


def _display_name(user) -> str:
    name = f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip()
    return name or getattr(user, "username", None) or getattr(user, "email", "Student")


class _ClassroomScopedView(APIView):
    permission_classes = [IsAuthenticated, IsClassMemberCap]

    def get_classroom(self) -> Classroom:
        if not hasattr(self, "_classroom"):
            self._classroom = get_object_or_404(Classroom, pk=self.kwargs["classroom_pk"])
        return self._classroom


class RankingsView(_ClassroomScopedView):
    def get(self, request, classroom_pk, kind):
        kind = kind.upper()
        if kind not in _VALID_KINDS:
            return Response({"detail": "Unknown ranking kind."}, status=status.HTTP_400_BAD_REQUEST)

        classroom = self.get_classroom()
        caps = classroom_capabilities(request.user, classroom)
        cfg, _ = ClassroomRankingConfig.objects.get_or_create(classroom=classroom)

        latest_period = (
            RankingSnapshot.objects.filter(classroom=classroom, kind=kind)
            .order_by("-computed_at")
            .values_list("period_key", flat=True)
            .first()
        )
        snaps = list(
            RankingSnapshot.objects.filter(classroom=classroom, kind=kind, period_key=latest_period)
            .select_related("student")
            .order_by("rank")
        ) if latest_period else []

        # Staff/admin see everything; students are governed by the config.
        staff = caps.is_staff
        mode = cfg.leaderboard_mode
        hide_scores = cfg.hide_score_values and not staff

        rows = []
        my_row = None
        for s in snaps:
            is_me = s.student_id == request.user.id
            show_name = staff or is_me or mode == ClassroomRankingConfig.MODE_FULL
            show_score = staff or is_me or not hide_scores
            row = {
                "rank": s.rank,
                "is_me": is_me,
                "name": _display_name(s.student) if show_name else f"Student #{s.rank}",
                "score": float(s.score) if show_score else None,
                "previous_rank": s.previous_rank,
                "rank_change": (s.components or {}).get("rank_change"),
                "trend": s.trend,
                "percentile": float(s.percentile) if s.percentile is not None else None,
                "confidence": s.confidence,
                "components": s.components if (staff or is_me) else None,
            }
            if is_me:
                my_row = row
            rows.append(row)

        # Students in HIDDEN mode only get their own row.
        if not staff and mode == ClassroomRankingConfig.MODE_HIDDEN:
            rows = [my_row] if my_row else []

        return Response({
            "kind": kind,
            "period_key": latest_period,
            "config": {"leaderboard_mode": mode, "hide_score_values": cfg.hide_score_values},
            "can_configure": caps.can_configure_ranking,
            "can_recompute": caps.can_recompute_ranking,
            "my": my_row,
            "rows": rows,
        })


class RankingRecomputeView(_ClassroomScopedView):
    permission_classes = [IsAuthenticated, CanRecomputeRanking]

    def post(self, request, classroom_pk):
        classroom = self.get_classroom()
        kinds = request.data.get("kinds") or ["SAT", "ACADEMIC"]
        kinds = tuple(k for k in kinds if k in _VALID_KINDS) or ("SAT", "ACADEMIC")
        summary = service.recompute_classroom(classroom, kinds=kinds)
        return Response({"status": "recomputed", "counts": summary})


class RankingConfigView(_ClassroomScopedView):
    """Teacher/owner sets leaderboard visibility (FULL/ANONYMOUS/HIDDEN + hide scores)."""

    permission_classes = [IsAuthenticated, CanConfigureRanking]

    def patch(self, request, classroom_pk):
        classroom = self.get_classroom()
        cfg, _ = ClassroomRankingConfig.objects.get_or_create(classroom=classroom)
        mode = request.data.get("leaderboard_mode")
        if mode is not None:
            if mode not in dict(ClassroomRankingConfig.MODE_CHOICES):
                return Response({"detail": "Invalid leaderboard_mode."}, status=status.HTTP_400_BAD_REQUEST)
            cfg.leaderboard_mode = mode
        if "hide_score_values" in request.data:
            cfg.hide_score_values = bool(request.data.get("hide_score_values"))
        cfg.updated_by = request.user
        cfg.save()
        return Response({"leaderboard_mode": cfg.leaderboard_mode, "hide_score_values": cfg.hide_score_values})


class RankingHistoryView(_ClassroomScopedView):
    """Historical ranking series for a student across snapshot periods (priority 9).

    Students may read only their own series; staff/admin may read any member's.
    """

    def get(self, request, classroom_pk, kind):
        kind = kind.upper()
        if kind not in _VALID_KINDS:
            return Response({"detail": "Unknown ranking kind."}, status=status.HTTP_400_BAD_REQUEST)
        classroom = self.get_classroom()
        caps = classroom_capabilities(request.user, classroom)

        requested = request.query_params.get("student")
        target_id = int(requested) if requested else request.user.id
        if target_id != request.user.id and not caps.is_staff:
            return Response({"detail": "Forbidden."}, status=status.HTTP_403_FORBIDDEN)

        rows = list(
            RankingSnapshot.objects.filter(classroom=classroom, kind=kind, student_id=target_id)
            .order_by("computed_at")
            .values("period_key", "rank", "score", "percentile", "trend", "computed_at")
        )
        history = [
            {
                "period_key": r["period_key"],
                "rank": r["rank"],
                "score": float(r["score"]),
                "percentile": float(r["percentile"]) if r["percentile"] is not None else None,
                "trend": r["trend"],
                "computed_at": r["computed_at"].isoformat(),
            }
            for r in rows
        ]
        return Response({"kind": kind, "student_id": target_id, "history": history})
