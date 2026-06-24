from __future__ import annotations

from rest_framework.throttling import SimpleRateThrottle

from .mitigation import is_classroom_mitigation_strict


class AssessmentAnswerPerAttemptThrottle(SimpleRateThrottle):
    """
    Per-attempt answer write throttle.

    Scope rate is configured under REST_FRAMEWORK.DEFAULT_THROTTLE_RATES['assessment_answer'].
    Key includes (user_id, attempt_id) so one student can't flood one attempt.
    """

    scope = "assessment_answer"

    def get_cache_key(self, request, view):
        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            return None
        attempt_id = None
        try:
            data = getattr(request, "data", None) or {}
            attempt_id = data.get("attempt_id")
        except Exception:
            attempt_id = None
        if attempt_id is None:
            # Fall back: throttle by user only (still prevents floods).
            return self.cache_format % {"scope": self.scope, "ident": str(user.pk)}
        return self.cache_format % {"scope": self.scope, "ident": f"{user.pk}:{attempt_id}"}


class AssessmentAssignHomeworkThrottle(SimpleRateThrottle):
    """
    Throttle the homework assignment endpoint (staff action).

    Scope rate is configured under REST_FRAMEWORK.DEFAULT_THROTTLE_RATES['assessment_assign'].
    Keyed by user id.
    """

    scope = "assessment_assign"

    def get_cache_key(self, request, view):
        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            return None
        return self.cache_format % {"scope": self.scope, "ident": str(user.pk)}


class AssessmentAssignHomeworkPerClassroomThrottle(SimpleRateThrottle):
    """
    Per-classroom limit on assessment homework assignments (shared across all staff).
    When mitigation marks a classroom, uses scope ``assessment_assign_classroom_mitigated`` (stricter).
    """

    scope = "assessment_assign_classroom"

    def allow_request(self, request, view):
        orig = self.scope
        try:
            try:
                data = getattr(request, "data", None) or {}
                cid = data.get("classroom_id")
                if cid is not None and is_classroom_mitigation_strict(int(cid)):
                    self.scope = "assessment_assign_classroom_mitigated"
            except Exception:
                pass
            return super().allow_request(request, view)
        finally:
            self.scope = orig

    def get_cache_key(self, request, view):
        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            return None
        try:
            data = getattr(request, "data", None) or {}
            cid = data.get("classroom_id")
            if cid is None:
                return None
            return self.cache_format % {"scope": self.scope, "ident": str(int(cid))}
        except Exception:
            return None


class AssessmentAssignHomeworkGlobalThrottle(SimpleRateThrottle):
    """
    System-wide limit on assessment homework assignments (all users, all classrooms).
    """

    scope = "assessment_assign_global"

    def get_cache_key(self, request, view):
        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            return None
        return self.cache_format % {"scope": self.scope, "ident": "global"}

