"""Classroom analytics API (read-only, computed live — no persisted cache).

GET /api/classes/<pk>/analytics/class/         staff: class health
GET /api/classes/<pk>/analytics/me/            member: own progress
GET /api/classes/<pk>/analytics/students/<id>/ staff or self: a student's progress
"""

from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response

from . import analytics as analytics_service
from .capabilities import classroom_capabilities
from .models import ClassroomMembership
from .views_rankings import _ClassroomScopedView


class AnalyticsClassView(_ClassroomScopedView):
    def get(self, request, classroom_pk):
        classroom = self.get_classroom()
        if not classroom_capabilities(request.user, classroom).is_staff:
            return Response({"detail": "Staff only."}, status=status.HTTP_403_FORBIDDEN)
        return Response(analytics_service.class_analytics(classroom))


class AnalyticsMeView(_ClassroomScopedView):
    def get(self, request, classroom_pk):
        classroom = self.get_classroom()  # IsClassMemberCap enforces membership
        return Response(analytics_service.student_analytics(classroom, request.user))


class AnalyticsStudentView(_ClassroomScopedView):
    def get(self, request, classroom_pk, student_id):
        classroom = self.get_classroom()
        caps = classroom_capabilities(request.user, classroom)
        if not caps.is_staff and request.user.id != int(student_id):
            return Response({"detail": "Forbidden."}, status=status.HTTP_403_FORBIDDEN)
        student = get_object_or_404(
            ClassroomMembership, classroom=classroom, user_id=student_id
        ).user
        return Response(analytics_service.student_analytics(classroom, student))
