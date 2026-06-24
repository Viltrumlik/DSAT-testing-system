from __future__ import annotations

from django.conf import settings
from django.http import JsonResponse
from django.middleware.csrf import CsrfViewMiddleware, get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView


def _is_same_site_origin(request) -> bool:
    """
    Strict origin check for unsafe API requests.
    Allows same-origin and trusted origins from settings.CSRF_TRUSTED_ORIGINS.
    """
    origin = str(request.headers.get("Origin") or "").strip()
    if not origin:
        # Some clients omit Origin; fall back to Referer check.
        referer = str(request.headers.get("Referer") or "").strip()
        origin = referer.split("/", 3)[:3]
        origin = "/".join(origin) if isinstance(origin, list) else ""
    if not origin:
        return False
    allowed = set(getattr(settings, "CSRF_TRUSTED_ORIGINS", []) or [])
    host = request.get_host()
    scheme = "https" if not getattr(settings, "DEBUG", False) else "http"
    allowed.add(f"{scheme}://{host}")
    return origin in allowed


class APICSRFEnforceMiddleware:
    """
    Enforce CSRF for cookie-authenticated API requests.

    DRF APIViews are CSRF-exempt by default, so we must enforce explicitly when the
    browser carries auth cookies (lms_access / lms_refresh).
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.csrf = CsrfViewMiddleware(get_response)

    def __call__(self, request):
        path = request.path or ""
        method = (request.method or "GET").upper()
        unsafe = method not in ("GET", "HEAD", "OPTIONS", "TRACE")

        if path.startswith("/api/") and unsafe:
            # Auth client telemetry — `navigator.sendBeacon` cannot attach X-CSRFToken.
            # Same-origin / trusted Origin only; payload is non-authoritative aggregates.
            if path.startswith("/api/auth/client-telemetry/"):
                if not _is_same_site_origin(request):
                    return JsonResponse({"detail": "Bad origin."}, status=403)
                return self.get_response(request)

            # Always require CSRF for auth endpoints, even before cookies exist.
            # This prevents "login works sometimes" issues across subdomains/sessions.
            enforce = path.startswith("/api/auth/") or bool(request.COOKIES.get("lms_access") or request.COOKIES.get("lms_refresh"))
            if enforce:
                if not _is_same_site_origin(request):
                    return JsonResponse({"detail": "Bad origin."}, status=403)
                # Validate token pair header+cookie.
                reason = self.csrf.process_view(request, callback=None, callback_args=(), callback_kwargs={})
                if reason is not None:
                    return JsonResponse({"detail": "CSRF failed."}, status=403)

        return self.get_response(request)


class CsrfTokenView(APIView):
    """
    Issue a CSRF cookie (csrftoken) for SPA clients.
    """

    permission_classes = []
    authentication_classes = []

    @method_decorator(ensure_csrf_cookie)
    def get(self, request):
        token = get_token(request)
        return Response({"csrfToken": token}, status=status.HTTP_200_OK)

