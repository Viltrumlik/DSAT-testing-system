"""Teacher assignment + admin governance endpoints for a classroom.

Teacher (teaching team):
  POST /api/classes/<pk>/assign-midterm/   { mock_exam_id }   assign an existing
        interactive midterm (MockExam kind=MIDTERM) to all enrolled students.

Admin (global admin) — governance only:
  POST /api/classes/<pk>/assign-teacher/      { user_id }   set the classroom teacher
  POST /api/classes/<pk>/transfer-ownership/  { user_id }   move the OWNER role

Assignment goes through the access engine's ClassroomService, whose enforcement
write-through grants real, usable access (legacy assigned_users) in the same
transaction — independent of the ACCESS_ENGINE read flags. No separate admin step.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status as http
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from access.engine.classroom_service import ClassroomAccessService
from access.resources import RT_MIDTERM
from exams.models import MockExam

from .capabilities import classroom_capabilities
from .models import Classroom, ClassroomMembership
from .views_rankings import _ClassroomScopedView

User = get_user_model()

# Classroom subject (ENGLISH/MATH) → midterm subject (READING_WRITING/MATH).
_CLASSROOM_TO_MIDTERM_SUBJECT = {
    Classroom.SUBJECT_MATH: "MATH",
    Classroom.SUBJECT_ENGLISH: "READING_WRITING",
}


class AssignMidtermView(_ClassroomScopedView):
    """Assign an existing interactive midterm to every enrolled student."""

    def post(self, request, classroom_pk):
        classroom = self.get_classroom()
        caps = classroom_capabilities(request.user, classroom)
        if not caps.can_manage_assignments:
            return Response(
                {"detail": "Only the teaching team can assign midterms."},
                status=http.HTTP_403_FORBIDDEN,
            )

        raw = request.data.get("mock_exam_id") or request.data.get("midterm_id")
        try:
            exam_id = int(raw)
        except (TypeError, ValueError):
            return Response({"detail": "mock_exam_id is required."}, status=http.HTTP_400_BAD_REQUEST)

        exam = MockExam.objects.filter(pk=exam_id).first()
        if exam is None or exam.kind != MockExam.KIND_MIDTERM:
            return Response({"detail": "Midterm not found."}, status=http.HTTP_404_NOT_FOUND)

        expected = _CLASSROOM_TO_MIDTERM_SUBJECT.get(classroom.subject)
        if expected and exam.midterm_subject != expected:
            return Response(
                {"detail": f"This midterm's subject does not match the classroom subject ({classroom.get_subject_display()})."},
                status=http.HTTP_400_BAD_REQUEST,
            )

        result = ClassroomAccessService.assign_resource_to_classroom(
            classroom, RT_MIDTERM, exam.id, actor=request.user, note="teacher midterm assignment",
        )
        return Response({"detail": "Midterm assigned to classroom.", **result}, status=http.HTTP_200_OK)


class _AdminClassroomGovernanceView(APIView):
    """Base for admin-only governance actions on a classroom."""

    permission_classes = [IsAuthenticated]

    def _guard(self, request) -> bool:
        # Governance (assign-teacher / transfer-ownership) is ADMIN-only by spec.
        # NOTE: do NOT use ``is_global_admin`` here — it treats any LMS-staff user
        # (including ordinary teachers, whose ``is_admin`` is permission-based) as a
        # global admin, which would let teachers reassign/transfer each other's
        # classrooms. Restrict strictly to super_admin / admin / Django superuser.
        u = request.user
        if not u or not getattr(u, "is_authenticated", False):
            return False
        if getattr(u, "is_superuser", False):
            return True
        return str(getattr(u, "role", "") or "").strip().lower() in ("super_admin", "admin")

    def _teacher_user(self, user_id):
        user = get_object_or_404(User, pk=user_id)
        role = str(getattr(user, "role", "") or "").strip().lower()
        return user, role


class AssignTeacherView(_AdminClassroomGovernanceView):
    """Admin sets the classroom's teacher (and ensures an active TEACHER membership)."""

    @transaction.atomic
    def post(self, request, classroom_pk):
        if not self._guard(request):
            return Response({"detail": "Admin only."}, status=http.HTTP_403_FORBIDDEN)
        classroom = get_object_or_404(Classroom, pk=classroom_pk)
        user, role = self._teacher_user(request.data.get("user_id"))
        if role not in ("teacher", "super_admin"):
            return Response({"detail": "User is not a teacher."}, status=http.HTTP_400_BAD_REQUEST)

        classroom.teacher = user
        classroom.save(update_fields=["teacher", "updated_at"])
        ClassroomMembership.objects.update_or_create(
            classroom=classroom,
            user=user,
            defaults={"role": ClassroomMembership.ROLE_TEACHER, "status": ClassroomMembership.STATUS_ACTIVE},
        )
        return Response({"detail": "Teacher assigned.", "classroom_id": classroom.pk, "teacher_id": user.pk})


class TransferOwnershipView(_AdminClassroomGovernanceView):
    """Admin transfers classroom ownership: demote current owner(s), promote the new owner."""

    @transaction.atomic
    def post(self, request, classroom_pk):
        if not self._guard(request):
            return Response({"detail": "Admin only."}, status=http.HTTP_403_FORBIDDEN)
        classroom = get_object_or_404(Classroom, pk=classroom_pk)
        user, role = self._teacher_user(request.data.get("user_id"))
        if role not in ("teacher", "super_admin"):
            return Response({"detail": "New owner must be a teacher."}, status=http.HTTP_400_BAD_REQUEST)

        ClassroomMembership.objects.filter(
            classroom=classroom,
            role__in=[ClassroomMembership.ROLE_OWNER, ClassroomMembership.ROLE_ADMIN],
        ).update(role=ClassroomMembership.ROLE_TEACHER)
        ClassroomMembership.objects.update_or_create(
            classroom=classroom,
            user=user,
            defaults={"role": ClassroomMembership.ROLE_OWNER, "status": ClassroomMembership.STATUS_ACTIVE},
        )
        classroom.teacher = user
        classroom.save(update_fields=["teacher", "updated_at"])
        return Response({"detail": "Ownership transferred.", "classroom_id": classroom.pk, "owner_id": user.pk})


class ClassroomGovernanceDeleteView(_AdminClassroomGovernanceView):
    """Admin governance: delete ANY classroom (admin / super_admin only).

    The operational ``ClassroomViewSet.destroy`` is owner-only and membership-scoped, so
    admins (non-members) get 403 there. This is the explicit governance delete path.
    """

    @transaction.atomic
    def delete(self, request, classroom_pk):
        if not self._guard(request):
            return Response({"detail": "Admin only."}, status=http.HTTP_403_FORBIDDEN)
        classroom = get_object_or_404(Classroom, pk=classroom_pk)
        classroom.delete()
        return Response(status=http.HTTP_204_NO_CONTENT)
