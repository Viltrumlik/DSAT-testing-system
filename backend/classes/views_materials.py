"""Classroom materials API — downloadable PDF/DOCX files a teacher uploads to a classroom.

GET  /api/classes/<pk>/materials/        list active materials (any class member)
POST /api/classes/<pk>/materials/        upload a material (staff: TA+Teacher+Owner)
DELETE /api/classes/<pk>/materials/<id>/ soft-archive a material (staff)

Materials are plain files (no attempts/scoring) — deliberately separate from the
interactive Midterm engine. Access to a material follows classroom membership; the
file itself is served by nginx from shared/media.
"""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from rest_framework import status as http
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from .capabilities import classroom_capabilities
from .models import ClassroomMaterial
from .serializers import ClassroomMaterialSerializer
from .views_rankings import _ClassroomScopedView


def _max_bytes() -> int:
    return int(getattr(settings, "CLASSROOM_SUBMISSION_MAX_FILE_BYTES", 15 * 1024 * 1024))


class ClassroomMaterialsView(_ClassroomScopedView):
    """List (members) and upload (staff) materials for one classroom."""

    parser_classes = [MultiPartParser, FormParser]

    def get(self, request, classroom_pk):
        classroom = self.get_classroom()
        qs = ClassroomMaterial.objects.filter(classroom=classroom, is_active=True)
        data = ClassroomMaterialSerializer(qs, many=True, context={"request": request}).data
        return Response({"results": data})

    def post(self, request, classroom_pk):
        classroom = self.get_classroom()
        caps = classroom_capabilities(request.user, classroom)
        if not caps.can_manage_assignments:
            return Response(
                {"detail": "Only the teaching team can upload materials."},
                status=http.HTTP_403_FORBIDDEN,
            )

        title = (request.data.get("title") or "").strip()
        upload = request.FILES.get("file")
        if not title:
            return Response({"detail": "Title is required."}, status=http.HTTP_400_BAD_REQUEST)
        if not upload:
            return Response({"detail": "A file is required."}, status=http.HTTP_400_BAD_REQUEST)
        if upload.size > _max_bytes():
            mb = _max_bytes() // (1024 * 1024)
            return Response({"detail": f"File exceeds the {mb} MB limit."}, status=http.HTTP_400_BAD_REQUEST)

        material = ClassroomMaterial(
            classroom=classroom,
            teacher=request.user,
            title=title,
            description=(request.data.get("description") or "").strip(),
            file=upload,
        )
        try:
            # Triggers the FileExtensionValidator (pdf/doc/docx) on the model field.
            material.full_clean(exclude=["teacher"])
        except DjangoValidationError as exc:
            return Response(
                {"detail": "Only PDF or Word documents are allowed.", "errors": exc.message_dict},
                status=http.HTTP_400_BAD_REQUEST,
            )
        material.save()
        data = ClassroomMaterialSerializer(material, context={"request": request}).data
        return Response(data, status=http.HTTP_201_CREATED)


class ClassroomMaterialDetailView(_ClassroomScopedView):
    """Soft-archive a material (staff only)."""

    def delete(self, request, classroom_pk, material_id):
        classroom = self.get_classroom()
        caps = classroom_capabilities(request.user, classroom)
        if not caps.can_manage_assignments:
            return Response(
                {"detail": "Only the teaching team can remove materials."},
                status=http.HTTP_403_FORBIDDEN,
            )
        material = get_object_or_404(
            ClassroomMaterial, pk=material_id, classroom=classroom, is_active=True
        )
        material.is_active = False
        material.save(update_fields=["is_active", "updated_at"])
        return Response(status=http.HTTP_204_NO_CONTENT)
