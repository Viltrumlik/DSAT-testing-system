from __future__ import annotations

"""
Host / subdomain routing is **defense in depth** (UX separation and coarse abuse reduction).

Authorization MUST NOT depend on this module: every API view still enforces role, platform
``subject``, and ``UserAccess`` via ``access.services.authorize`` and related checks.
"""

from dataclasses import dataclass

from django.http import JsonResponse

from exams.metrics import incr as exams_metric_incr


@dataclass(frozen=True)
class HostGuardConfig:
    admin_prefix: str = "admin."
    questions_prefix: str = "questions."
    teacher_prefix: str = "teacher."


def _host_kind(host: str, cfg: HostGuardConfig) -> str:
    """
    Detect console from Host label.

    ``questions.mastersat.uz`` and ``www.questions.mastersat.uz`` (and ``api.questions.…``)
    must all resolve to ``questions``. A plain ``startswith("questions.")`` misses
    ``www.questions.…``, which kept ``lms_console=main`` and mislabeled the console in middleware.
    """
    h = (host or "").split(":")[0].lower()
    labels = [p for p in h.split(".") if p]
    if not labels:
        return "main"
    if labels[0] == "admin" or h.startswith(cfg.admin_prefix):
        return "admin"
    if labels[0] == "questions" or h.startswith(cfg.questions_prefix):
        return "questions"
    if len(labels) >= 2 and labels[1] == "questions":
        return "questions"
    if labels[0] == "teacher" or h.startswith(cfg.teacher_prefix):
        return "teacher"
    return "main"


class SubdomainAPIGuardMiddleware:
    """
    Enforce coarse separation of consoles by subdomain:
    - admin.<domain>: users + bulk assign; LMS exam authoring SPA (pastpapers, mocks,
      questions CRUD via ``/api/exams/admin/…`` — same-origin as apex; enforced in DRF)
    - questions.<domain>: preferred authoring subdomain; full ``/api/exams/admin/*`` + assessments admin
    - teacher.<domain>: teacher workspace APIs (classes + exams data); teacher + super_admin only
    - main domain: student portal APIs; exams authoring requires DRF roles
      (``/api/exams/admin/*`` is not HTTP-blocked here for same-origin SPAs).
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.cfg = HostGuardConfig()

    def __call__(self, request):
        path = request.path or ""
        host = request.get_host()
        kind = _host_kind(host, self.cfg)
        method = (request.method or "GET").upper()
        # Make console kind available to downstream handlers (views/serializers/etc).
        setattr(request, "lms_console", kind)

        # Non-API paths are unaffected.
        if not path.startswith("/api/"):
            return self.get_response(request)

        # Auth endpoints always allowed.
        if path.startswith("/api/auth/"):
            return self.get_response(request)

        # Health + schema endpoints must always be reachable (for load balancers and deploy checks).
        if path.startswith("/api/health/"):
            return self.get_response(request)
        if path.startswith("/api/schema/"):
            return self.get_response(request)

        if path.startswith("/api/csp-report/"):
            return self.get_response(request)

        # Assessment homework POST is allowed on the assignment consoles only:
        # admin (legacy ops) and teacher (teacher portal owns classroom assignment).
        # Never on questions.* or the apex/main API host.
        if path.startswith("/api/assessments/homework/assign/") and method == "POST" and kind not in ("admin", "teacher"):
            exams_metric_incr("forbidden_admin_route_total")
            return JsonResponse(
                {"detail": "Assessment homework assignment is available on the admin or teacher console only."},
                status=403,
            )

        # Ops: Alertmanager webhook (infrastructure).
        if path.startswith("/api/ops/alertmanager/"):
            return self.get_response(request)

        # Role-level gate (before endpoint allowlists).
        # - testers (test_admin) may use admin console for users/bulk-assign
        # - testers MAY use questions console subdomain
        u = getattr(request, "user", None)
        role = (
            str(getattr(u, "role", "") or "").strip().lower()
            if u and getattr(u, "is_authenticated", False)
            else ""
        )
        if kind == "admin" and role in ("student",):
            exams_metric_incr("forbidden_admin_route_total")
            return JsonResponse(
                {"detail": "You cannot access admin console."}, status=403
            )
        if kind == "questions" and role == "student":
            exams_metric_incr("forbidden_admin_route_total")
            return JsonResponse(
                {"detail": "Students cannot access questions console."}, status=403
            )

        # Admin subdomain: bulk assign + users + read-only exam lists.
        if kind == "admin":
            if path.startswith("/api/users/"):
                return self.get_response(request)
            if path.startswith("/api/access/"):
                return self.get_response(request)
            if path.startswith("/api/classes/"):
                return self.get_response(request)
            if path.startswith("/api/exams/bulk_assign"):
                return self.get_response(request)
            if path.startswith("/api/exams/bulk_assign/"):
                return self.get_response(request)
            if path.startswith("/api/exams/assignments/"):
                return self.get_response(request)
            # Hosted admin SPA performs full exam authoring (pastpaper packs, mock shells, tests/modules/questions).
            # Same policy as apex domain: do not deny by host; rely on ``CanManageQuestions`` etc.
            if path.startswith("/api/exams/admin/"):
                return self.get_response(request)
            # Assessments: admin assigns sets as homework + needs to list sets.
            if path.startswith("/api/assessments/"):
                # Allow homework assignment and read-only browsing on admin console.
                if path.startswith("/api/assessments/homework/assign/"):
                    return self.get_response(request)
                if path.startswith("/api/assessments/admin/"):
                    if method == "GET":
                        return self.get_response(request)
                    exams_metric_incr("forbidden_admin_route_total")
                    return JsonResponse(
                        {"detail": "Assessment authoring is disabled on admin subdomain. Use questions subdomain."},
                        status=403,
                    )
                # Student attempt flows live on main domain; block on admin for clarity.
                exams_metric_incr("forbidden_admin_route_total")
                return JsonResponse(
                    {"detail": "This assessments endpoint is not available on admin subdomain."}, status=403
                )
            exams_metric_incr("forbidden_admin_route_total")
            return JsonResponse(
                {"detail": "This endpoint is not available on admin subdomain."}, status=403
            )

        # Questions subdomain: exams admin CRUD endpoints.
        if kind == "questions":
            # Auth bootstrap must work across consoles. `/api/users/me/` is required for
            # Next.js session boot + projection cookie refresh on every subdomain.
            if path.startswith("/api/users/me/"):
                return self.get_response(request)
            if path.startswith("/api/exams/admin/"):
                return self.get_response(request)
            # Assessments authoring CRUD endpoints live here (create/edit/delete sets/questions).
            if path.startswith("/api/assessments/admin/"):
                return self.get_response(request)
            # Assignment dispatch is admin-subdomain only.  Explicitly block so the
            # catch-all return below does not accidentally permit these paths.
            if path.startswith("/api/exams/bulk_assign") or path.startswith("/api/exams/assignments/"):
                exams_metric_incr("forbidden_admin_route_total")
                return JsonResponse(
                    {"detail": "Assignment dispatch is available on admin subdomain only."},
                    status=403,
                )
            # Users are intentionally not available here.
            if path.startswith("/api/users/"):
                exams_metric_incr("forbidden_admin_route_total")
                return JsonResponse({"detail": "Users console is available on admin subdomain."}, status=403)
            return self.get_response(request)

        # Teacher subdomain: teacher workspace APIs only, restricted to teacher + super_admin.
        # This rule is intentionally role-based (not permission-based): admin and test_admin
        # are denied here even though they hold staff permissions elsewhere.
        if kind == "teacher":
            # Auth bootstrap must work for everyone (returns the user or 401); required for
            # the Next.js session boot + projection cookie refresh on this subdomain.
            if path.startswith("/api/users/me/"):
                return self.get_response(request)
            if role not in ("teacher", "super_admin"):
                exams_metric_incr("forbidden_admin_route_total")
                return JsonResponse(
                    {"detail": "You do not have permission to access the Teacher Portal."},
                    status=403,
                )
            # Teacher-facing namespaces: classes + exams data powering the workspace,
            # plus the read-only exam-dates lookup used by analytics.
            if path.startswith("/api/classes/"):
                return self.get_response(request)
            if path.startswith("/api/exams/"):
                return self.get_response(request)
            if path.startswith("/api/users/admin/exam-dates/"):
                return self.get_response(request)
            # Assessment HOMEWORK surface (assign + per-classroom results/gradebook).
            # Assessment authoring (``/api/assessments/admin/``) stays on the questions console.
            if path.startswith("/api/assessments/homework/"):
                return self.get_response(request)
            exams_metric_incr("forbidden_admin_route_total")
            return JsonResponse(
                {"detail": "This endpoint is not available on the teacher portal."},
                status=403,
            )

        # Main domain: do **not** block ``/api/exams/admin/`` here. JWT attaches the user early
        # via ``JWTUserMiddleware``, but authoring permission is enforced in DRF views
        # (``CanManageQuestions``); blocking HTTP here broke single-origin SPA deployments where
        # the CMS calls the API on the same host as students.

        return self.get_response(request)

