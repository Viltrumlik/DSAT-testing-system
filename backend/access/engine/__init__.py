"""
Centralized access engine (Phase 2).

Service layer for the hybrid SUBJECT + RESOURCE access model. Import the
services from here:

    from access.engine import AccessService, AssignmentService, VisibilityService, ClassroomAccessService

All behavior is flag-gated (see :mod:`access.engine.flags`) and inert in
production until the ``ACCESS_ENGINE_*`` settings are enabled.
"""

from .access_service import AccessService
from .assignment_service import AssignmentService
from .visibility_service import VisibilityService
from .classroom_service import ClassroomAccessService

__all__ = [
    "AccessService",
    "AssignmentService",
    "VisibilityService",
    "ClassroomAccessService",
]
