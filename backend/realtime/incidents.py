from __future__ import annotations

from rest_framework import status
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import IncidentReview


class IncidentReviewListCreateView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        rows = IncidentReview.objects.order_by("-started_at", "-id")[:200]
        return Response([r.to_dict() for r in rows], status=status.HTTP_200_OK)

    def post(self, request):
        data = request.data if isinstance(request.data, dict) else {}
        row = IncidentReview.from_payload(data=data, actor=getattr(request, "user", None))
        return Response(row.to_dict(), status=status.HTTP_201_CREATED)


class IncidentReviewDetailView(APIView):
    permission_classes = [IsAdminUser]

    def patch(self, request, pk: int):
        row = IncidentReview.objects.filter(pk=pk).first()
        if not row:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        data = request.data if isinstance(request.data, dict) else {}
        row.apply_patch(data=data, actor=getattr(request, "user", None))
        return Response(row.to_dict(), status=status.HTTP_200_OK)

