import logging

from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.views import TokenRefreshView
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
from rest_framework_simplejwt.tokens import RefreshToken
from django.db.models import Prefetch, Q
from .models import ExamDateOption, User
from classes.models import Classroom, ClassroomMembership
from access import constants as acc_const
from access.permissions import HasManageUsers, HasManageUsersOrAssignTestAccess
from access.services import (
    actor_subject_probe_for_domain_perm,
    authorize,
    get_effective_permission_codenames,
    is_global_scope_staff,
    normalized_role,
    user_domain_subject,
)

from .serializers import (
    ExamDateOptionPublicSerializer,
    ExamDateOptionSerializer,
    MyTokenObtainPairSerializer,
    SecurityAuditEventSerializer,
    UserMeSerializer,
    UserSerializer,
)
from .permissions import IsAuthenticatedAndNotFrozen
from django.conf import settings
from django.http import HttpResponseRedirect
from django.utils import timezone
import re
import time
from datetime import timedelta
from django.core.cache import cache
from time import monotonic

from .security_audit import log_security_event
from .security_risk import clear_security_step_up, record_failed_refresh_attempt
from .telegram_oidc import (
    TelegramOIDCError,
    build_authorize_url,
    exchange_code_for_tokens,
    telegram_user_id_from_claims,
    verify_telegram_id_token,
)
from .phone_utils import normalize_phone
from .telegram_bot_info import telegram_bot_username_for_token
from .authentication import CookieOrHeaderJWTAuthentication
from .auth_cookies import clear_auth_cookies, set_access_cookie, set_auth_cookies, REFRESH_COOKIE
from .auth_correlation_controls import escalate_on_telemetry_anomaly
from .client_auth_telemetry import score_telemetry_anomalies, validate_client_auth_telemetry_body
from .security_metrics import incr as security_metric_incr
from core.metrics import incr as metric_incr, incr_role as metric_incr_role
from core.drills import env_flag
from .security_churn import observe_new_session, observe_refresh_rotation
from .models import RefreshSession
from django.utils import timezone

logger = logging.getLogger("security.users")


def _subject_for_auth_response(user: User) -> str:
    """Domain subject for staff (math|english); empty for students without subject."""
    return getattr(user, "subject", None) or ""


def _prefetch_user_directory(qs):
    """Avoid N+1 when serializing ``bulk_assign_profile`` for list views."""
    return qs.prefetch_related(
        "access_grants",
        Prefetch(
            "class_memberships",
            queryset=ClassroomMembership.objects.filter(role=ClassroomMembership.ROLE_STUDENT).select_related(
                "classroom"
            ),
        ),
    )


def _apply_telegram_phone(user, data) -> Response | None:
    """Persist verified phone from Telegram payload; return error Response or None."""
    raw_phone = data.get("phone_number")
    if raw_phone is None or not str(raw_phone).strip():
        return None
    try:
        normalized = normalize_phone(raw_phone)
    except ValueError:
        return Response({"detail": "Invalid phone number."}, status=status.HTTP_400_BAD_REQUEST)
    if not normalized:
        return None
    if User.objects.filter(phone_number=normalized).exclude(pk=user.pk).exists():
        return Response(
            {"detail": "This phone number is already in use."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    user.phone_number = normalized
    user.save(update_fields=["phone_number"])
    return None


def _effective_telegram_bot_username() -> str:
    u = getattr(settings, "TELEGRAM_BOT_USERNAME", "") or ""
    if u:
        return u
    token = getattr(settings, "TELEGRAM_BOT_TOKEN", "") or ""
    if not token:
        return ""
    return telegram_bot_username_for_token(token)


def _telegram_oidc_client_id() -> str:
    """The OIDC ``client_id`` (== Telegram bot id). Prefers explicit setting, falls back to bot token prefix."""
    explicit = (getattr(settings, "TELEGRAM_OIDC_CLIENT_ID", "") or "").strip()
    if explicit:
        return explicit
    token = (getattr(settings, "TELEGRAM_BOT_TOKEN", "") or "").strip().strip('"').strip("'")
    if not token or ":" not in token:
        return ""
    bot_id = token.split(":", 1)[0].strip()
    return bot_id if bot_id.isdigit() else ""


def _telegram_oidc_client_secret() -> str:
    return (getattr(settings, "TELEGRAM_OIDC_CLIENT_SECRET", "") or "").strip()


def _telegram_oidc_redirect_uri() -> str:
    return (getattr(settings, "TELEGRAM_OIDC_REDIRECT_URI", "") or "").strip()


def _verified_telegram_oidc_payload(request_data):
    # type: (object) -> tuple
    """Verify the ``id_token`` from the request body. Returns (claims, None) on success
    or (None, error_response) on failure. Caller can then read tg_id / name / phone from claims.
    """
    client_id = _telegram_oidc_client_id()
    if not client_id:
        return None, Response(
            {"detail": "Telegram sign-in is not configured on the server."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    id_token = str(request_data.get("id_token") or "").strip()
    if not id_token:
        return None, Response({"detail": "Missing id_token."}, status=status.HTTP_400_BAD_REQUEST)
    try:
        claims = verify_telegram_id_token(id_token, expected_audience=client_id)
    except TelegramOIDCError as exc:
        return None, Response(
            {"detail": "Invalid or expired Telegram sign-in.", "code": "oidc_invalid"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return claims, None


def _apply_telegram_phone_from_claims(user, claims) -> Response | None:
    """OIDC variant of _apply_telegram_phone. Reads phone_number directly from verified claims."""
    raw_phone = claims.get("phone_number") if claims else None
    if raw_phone is None or not str(raw_phone).strip():
        return None
    return _apply_telegram_phone(user, {"phone_number": raw_phone})

class ThrottledTokenObtainPairView(TokenObtainPairView):
    serializer_class = MyTokenObtainPairSerializer
    throttle_classes = []


def _revoked_key(jti: str) -> str:
    return f"auth.revoked_refresh_jti.{jti}"


def _is_refresh_revoked(refresh: str) -> bool:
    try:
        tok = RefreshToken(refresh)
        jti = str(tok.get("jti") or "")
        if not jti:
            return False
        return bool(cache.get(_revoked_key(jti)))
    except Exception:
        return False


def _revoke_refresh(refresh: str) -> None:
    """
    Lightweight refresh revoke without DB migrations:
    store refresh jti in shared cache until its exp.
    """
    try:
        tok = RefreshToken(refresh)
        jti = str(tok.get("jti") or "")
        exp = int(tok.get("exp") or 0)
        if not jti or not exp:
            return
        ttl = max(1, exp - int(time.time()))
        cache.set(_revoked_key(jti), "1", timeout=ttl)
    except Exception:
        # Log the failure — silent swallow here meant a successful logout could leave the
        # refresh token usable if the cache was unreachable. We still don't re-raise
        # (logout endpoints should remain idempotent and best-effort).
        logger.exception("refresh_revoke_failed")


def _jti_of_refresh(refresh: str) -> str:
    tok = RefreshToken(refresh)
    return str(tok.get("jti") or "")


def _user_id_of_refresh(refresh: str) -> int | None:
    tok = RefreshToken(refresh)
    uid = tok.get("user_id")
    try:
        return int(uid)
    except Exception:
        return None


def _audit_refresh_failure(*, user_id: int | None, request, kind: str) -> None:
    record_failed_refresh_attempt(user_id)
    if user_id is not None and kind in (
        "replay_revoked_cache",
        "replay_no_session",
        "concurrent_rotation",
    ):
        log_security_event(
            user_id=user_id,
            event_type="refresh_replay_blocked",
            request=request,
            detail={"kind": kind},
            severity="warning",
        )


def _session_fingerprint(request) -> tuple[str, str]:
    ip = str(request.META.get("REMOTE_ADDR") or "")[:64]
    ua = str(request.META.get("HTTP_USER_AGENT") or "")[:512]
    return ip, ua


class CookieTokenObtainPairView(ThrottledTokenObtainPairView):
    """
    Browser auth: set HttpOnly cookies for access+refresh.
    Response body omits raw tokens to avoid JS-readable auth.
    """

    def post(self, request, *args, **kwargs):
        t0 = monotonic()
        # Legacy clients may still read JSON tokens; keep compatibility via opt-in.
        include_tokens = str(request.query_params.get("include_tokens") or "").lower() in ("1", "true", "yes")
        remember_me = str(request.data.get("remember_me") or "1").lower() in ("1", "true", "yes")
        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except Exception:
            # Best-effort reason classification for staff consoles (admin/questions).
            # Keep the external "detail" stable to avoid account enumeration on the main domain.
            reason = "invalid_credentials"
            console = str(getattr(request, "lms_console", "") or "").strip().lower()
            ident = str(request.data.get("email") or request.data.get("username") or "").strip()
            if console in ("admin", "questions") and ident:
                try:
                    from django.contrib.auth import get_user_model
                    from django.db.models import Q

                    U = get_user_model()
                    u = U.objects.filter(Q(email__iexact=ident) | Q(username__iexact=ident)).first()
                    if not u:
                        reason = "user_not_found"
                    elif not bool(getattr(u, "is_active", True)):
                        reason = "inactive"
                    elif not u.check_password(str(request.data.get("password") or "")):
                        reason = "bad_password"
                    else:
                        reason = "auth_failed"
                except Exception:
                    reason = "auth_failed"

            security_metric_incr("failed_login", 1)
            metric_incr("slo_login_fail_total")
            metric_incr_role("slo_login_fail_total", actor=getattr(serializer, "user", None) or getattr(request, "user", None))
            logger.info(
                "login_failed reason=%s host=%s ident=%s",
                reason,
                str(request.get_host() or ""),
                ident[:128],
            )
            body = {"detail": "Invalid credentials."}
            if console in ("admin", "questions"):
                body["code"] = reason
            return Response(body, status=status.HTTP_401_UNAUTHORIZED)

        # Login funnel: enforce the teacher-portal access boundary at the auth layer.
        # Credentials are already valid here; this is an authorization gate, not enumeration.
        #   - teacher.* : only teacher + super_admin may obtain a session.
        #   - main domain: teacher accounts must use the Teacher Portal; refuse here so a
        #     teacher can only enter via teacher.mastersat.uz.
        # Returning before set_auth_cookies means no cookies and no session row are created.
        login_console = str(getattr(request, "lms_console", "") or "").strip().lower()
        login_user = getattr(serializer, "user", None)
        login_role = str(getattr(login_user, "role", "") or "").strip().lower()
        if login_console == "teacher" and login_role not in ("teacher", "super_admin"):
            return Response(
                {"detail": "You do not have permission to access the Teacher Portal."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if login_console == "main" and login_role == "teacher":
            return Response(
                {"detail": "Teachers must sign in at the Teacher Portal: https://teacher.mastersat.uz"},
                status=status.HTTP_403_FORBIDDEN,
            )

        data = dict(serializer.validated_data)
        access = str(data.get("access") or "")
        refresh = str(data.get("refresh") or "")

        resp = Response(data, status=status.HTTP_200_OK)
        if access and refresh:
            set_auth_cookies(response=resp, request=request, access=access, refresh=refresh, remember_me=remember_me)
            try:
                user = getattr(serializer, "user", None)
                jti = _jti_of_refresh(refresh)
                if user is not None and jti:
                    ip, ua = _session_fingerprint(request)
                    RefreshSession.objects.update_or_create(
                        refresh_jti=jti,
                        defaults={"user": user, "revoked_at": None, "ip": ip, "user_agent": ua},
                    )
                    observe_new_session(user_id=int(user.pk), ip=ip, request=request)
            except Exception:
                pass

        if not include_tokens:
            resp.data.pop("access", None)
            resp.data.pop("refresh", None)
        metric_incr("slo_login_ok_total")
        metric_incr_role("slo_login_ok_total", actor=getattr(serializer, "user", None))
        metric_incr("slo_login_latency_ms_sum", int((monotonic() - t0) * 1000))
        metric_incr("slo_login_latency_ms_count")
        return resp


class CookieTokenRefreshView(TokenRefreshView):
    """
    Refresh using HttpOnly refresh cookie; sets new HttpOnly access cookie.
    """

    def post(self, request, *args, **kwargs):
        if env_flag("DRILL_REFRESH_OUTAGE"):
            return Response(
                {"detail": "Token refresh temporarily unavailable (drill)."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        include_tokens = str(request.query_params.get("include_tokens") or "").lower() in ("1", "true", "yes")

        refresh_cookie = request.COOKIES.get(REFRESH_COOKIE) if hasattr(request, "COOKIES") else None
        refresh_body = (request.data or {}).get("refresh") if hasattr(request, "data") else None
        refresh = str(refresh_cookie or refresh_body or "")
        if not refresh:
            security_metric_incr("refresh_fail", 1)
            return Response({"detail": "Missing refresh token."}, status=status.HTTP_400_BAD_REQUEST)
        if _is_refresh_revoked(refresh):
            _audit_refresh_failure(
                user_id=_user_id_of_refresh(refresh), request=request, kind="replay_revoked_cache"
            )
            security_metric_incr("refresh_fail", 1)
            return Response({"detail": "Refresh token revoked."}, status=status.HTTP_401_UNAUTHORIZED)

        # Enforce server-side session allowlist + rotation transactionally.
        try:
            jti = _jti_of_refresh(refresh)
            if not jti:
                raise ValueError("missing jti")
            s = RefreshSession.objects.filter(refresh_jti=jti, revoked_at__isnull=True).select_for_update().first()
            if not s:
                _audit_refresh_failure(
                    user_id=_user_id_of_refresh(refresh), request=request, kind="replay_no_session"
                )
                security_metric_incr("refresh_fail", 1)
                return Response({"detail": "Session revoked."}, status=status.HTTP_401_UNAUTHORIZED)
        except Exception:
            security_metric_incr("refresh_fail", 1)
            return Response({"detail": "Session validation failed."}, status=status.HTTP_401_UNAUTHORIZED)

        # Validate the provided refresh token cryptographically.
        try:
            serializer = TokenRefreshSerializer(data={"refresh": refresh})
            serializer.is_valid(raise_exception=True)
        except Exception:
            _audit_refresh_failure(user_id=_user_id_of_refresh(refresh), request=request, kind="invalid_token")
            security_metric_incr("refresh_fail", 1)
            return Response({"detail": "Invalid refresh token."}, status=status.HTTP_401_UNAUTHORIZED)

        # Full rotation: old revoked + new created atomically.
        from django.db import transaction
        from users.models import User

        ip, ua = _session_fingerprint(request)
        with transaction.atomic():
            s = RefreshSession.objects.select_for_update().filter(pk=s.pk, revoked_at__isnull=True).first()
            if not s:
                _audit_refresh_failure(
                    user_id=_user_id_of_refresh(refresh), request=request, kind="concurrent_rotation"
                )
                security_metric_incr("refresh_fail", 1)
                return Response({"detail": "Session revoked."}, status=status.HTTP_401_UNAUTHORIZED)

            user = User.objects.get(pk=s.user_id)
            try:
                step_until = getattr(user, "security_step_up_required_until", None)
                if step_until and step_until > timezone.now():
                    security_metric_incr("refresh_fail", 1)
                    return Response(
                        {"detail": "Re-authentication required.", "code": "security_step_up"},
                        status=status.HTTP_401_UNAUTHORIZED,
                    )
            except Exception:
                pass
            new_refresh = RefreshToken.for_user(user)
            new_refresh_s = str(new_refresh)
            new_access = str(new_refresh.access_token)
            new_jti = str(new_refresh.get("jti") or "")
            if not new_jti:
                _audit_refresh_failure(user_id=int(s.user_id), request=request, kind="rotation_no_jti")
                security_metric_incr("refresh_fail", 1)
                return Response({"detail": "Refresh rotation failed."}, status=status.HTTP_401_UNAUTHORIZED)

            # Mark old revoked in DB first.
            RefreshSession.objects.filter(pk=s.pk).update(revoked_at=timezone.now())

            # Create new session row (unique on refresh_jti prevents duplicates).
            RefreshSession.objects.update_or_create(
                refresh_jti=new_jti,
                defaults={"user": user, "revoked_at": None, "ip": ip, "user_agent": ua},
            )

        # After commit: revoke old jti in cache (best-effort) and touch churn counters.
        try:
            _revoke_refresh(refresh)
        except Exception:
            pass
        observe_refresh_rotation(user_id=int(s.user_id), ip=ip, request=request)
        security_metric_incr("refresh_rotations", 1)

        resp = Response({"access": new_access} if include_tokens else {}, status=status.HTTP_200_OK)
        set_auth_cookies(response=resp, request=request, access=new_access, refresh=new_refresh_s, remember_me=True)
        return resp


class CookieLogoutView(APIView):
    """
    Clear cookies and revoke the current refresh token (best-effort).
    """

    permission_classes = []

    def post(self, request):
        refresh = request.COOKIES.get(REFRESH_COOKIE) if hasattr(request, "COOKIES") else None
        if refresh:
            try:
                _revoke_refresh(str(refresh))
            except Exception:
                security_metric_incr("logout_revoke_fail", 1)
            try:
                jti = _jti_of_refresh(str(refresh))
                if jti:
                    RefreshSession.objects.filter(refresh_jti=jti, revoked_at__isnull=True).update(revoked_at=timezone.now())
            except Exception:
                pass
        resp = Response({"ok": True}, status=status.HTTP_200_OK)
        clear_auth_cookies(response=resp, request=request)
        return resp


class SessionListView(APIView):
    permission_classes = [IsAuthenticatedAndNotFrozen]

    def get(self, request):
        qs = RefreshSession.objects.filter(user=request.user).order_by("-last_seen_at", "-id")[:50]
        rows = []
        for s in qs:
            rows.append(
                {
                    "id": s.id,
                    "created_at": s.created_at.isoformat() if s.created_at else None,
                    "last_seen_at": s.last_seen_at.isoformat() if s.last_seen_at else None,
                    "ip": s.ip,
                    "user_agent": s.user_agent,
                    "revoked_at": s.revoked_at.isoformat() if s.revoked_at else None,
                }
            )
        return Response({"sessions": rows}, status=status.HTTP_200_OK)


class RevokeAllSessionsView(APIView):
    permission_classes = [IsAuthenticatedAndNotFrozen]

    def post(self, request):
        now = timezone.now()
        qs = RefreshSession.objects.filter(user=request.user, revoked_at__isnull=True)
        jtis = list(qs.values_list("refresh_jti", flat=True)[:500])
        for jti in jtis:
            try:
                cache.set(_revoked_key(str(jti)), "1", timeout=int(timedelta(days=8).total_seconds()))
            except Exception:
                pass
        qs.update(revoked_at=now)
        log_security_event(
            user_id=int(request.user.pk),
            event_type="session_revoke_all",
            request=request,
            detail={"sessions": len(jtis)},
            severity="info",
        )
        resp = Response({"ok": True}, status=status.HTTP_200_OK)
        clear_auth_cookies(response=resp, request=request)
        return resp


class RevokeSessionView(APIView):
    permission_classes = [IsAuthenticatedAndNotFrozen]

    def post(self, request, session_id: int):
        s = RefreshSession.objects.filter(pk=session_id, user=request.user).first()
        if not s:
            return Response({"detail": "Session not found."}, status=status.HTTP_404_NOT_FOUND)
        if s.revoked_at is None:
            RefreshSession.objects.filter(pk=s.pk).update(revoked_at=timezone.now())
            try:
                cache.set(_revoked_key(str(s.refresh_jti)), "1", timeout=int(timedelta(days=8).total_seconds()))
            except Exception:
                pass
            log_security_event(
                user_id=int(request.user.pk),
                event_type="session_revoke",
                request=request,
                detail={"session_id": int(session_id), "jti": str(s.refresh_jti)[:16]},
                severity="info",
            )
        return Response({"ok": True}, status=status.HTTP_200_OK)


class ClientAuthTelemetryIngestView(APIView):
    """
    Best-effort batch sink for SPA auth concurrency telemetry (logs + Prometheus-friendly counters).

    Responses are deliberately tiny; ingestion is gated by Api CSRF middleware for /api/auth/*.
    Payload is aggregates + recent client events — no persisted PII requirement.
    """

    # Truly anonymous best-effort ingest. Stale JWT cookies generated thousands of
    # 401 log entries on every page navigation while logged-out users had the SPA open
    # — auth provides no value here (no user identity used downstream).
    authentication_classes = []
    permission_classes = []
    parser_classes = [JSONParser]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "client_auth_telemetry"
    MAX_BODY_BYTES = 262_144

    def post(self, request):
        try:
            declared = int(request.META.get("CONTENT_LENGTH") or "0") or 0
        except (TypeError, ValueError):
            declared = 0
        raw_len = declared if declared > 0 else len(request.body or b"")

        if raw_len > self.MAX_BODY_BYTES:
            return Response(
                {"detail": "Payload too large."},
                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )

        body = request.data if isinstance(request.data, dict) else {}
        ok, err_code = validate_client_auth_telemetry_body(body)
        if not ok:
            security_metric_incr("client_auth_telemetry_rejected_total")
            return Response({"detail": "Invalid payload.", "code": err_code}, status=status.HTTP_400_BAD_REQUEST)

        events = body.get("events") or []
        events_len = len(events) if isinstance(events, list) else 0
        client_ts = int(body.get("client_ts") or 0)
        now_ms = int(time.time() * 1000)
        anomaly_flags = score_telemetry_anomalies(body, events_len, client_ts, now_ms)

        security_metric_incr("client_auth_telemetry_batches_total")

        correlation_headers = {
            "x_mastersat_auth_boot": request.META.get("HTTP_X_MASTERSAT_AUTH_BOOT"),
            "x_mastersat_auth_loss_active": request.META.get("HTTP_X_MASTERSAT_AUTH_LOSS_ACTIVE"),
            "x_mastersat_auth_loss_ver": request.META.get("HTTP_X_MASTERSAT_AUTH_LOSS_VER"),
            "x_mastersat_auth_recovery_ver": request.META.get("HTTP_X_MASTERSAT_AUTH_RECOVERY_VER"),
            "x_mastersat_auth_loss_reason": request.META.get("HTTP_X_MASTERSAT_AUTH_LOSS_REASON"),
            "x_mastersat_me_guard_depth": request.META.get("HTTP_X_MASTERSAT_ME_GUARD_DEPTH"),
        }
        log_payload = {
            "schema": body.get("schema"),
            "events_len": events_len,
            "client_ts": client_ts,
            "snapshot": body.get("snapshot"),
            "correl": body.get("correl"),
            "headers": correlation_headers,
            "anomaly_flags": anomaly_flags,
        }
        if anomaly_flags:
            security_metric_incr("client_auth_telemetry_anomaly_batches_total")
            escalate_on_telemetry_anomaly(request, anomaly_flags)
            logger.warning("client_auth_telemetry ingest suspicious %s", log_payload)
        else:
            logger.info("client_auth_telemetry ingest ok %s", log_payload)

        return Response(status=status.HTTP_204_NO_CONTENT)


class UserListView(generics.ListAPIView):
    serializer_class = UserSerializer
    permission_classes = [HasManageUsersOrAssignTestAccess]

    def list(self, request, *args, **kwargs):
        """
        Defensive wrapper: this endpoint is heavily used by the admin console.
        If a production schema/config drift causes an exception, return a structured 500 so
        staff can report the exact failure quickly (backend logs also capture traceback).
        """
        try:
            return super().list(request, *args, **kwargs)
        except Exception as exc:
            actor = getattr(request, "user", None)
            role = normalized_role(actor)
            logger.exception(
                "users.list failed actor_id=%s role=%s host=%s path=%s",
                getattr(actor, "pk", None),
                role,
                getattr(request, "get_host", lambda: "")(),
                getattr(request, "path", ""),
            )
            # Only reveal exception details to superusers / super_admin (staff console only).
            reveal = bool(getattr(actor, "is_superuser", False) or role == acc_const.ROLE_SUPER_ADMIN)
            body = {"detail": "Could not load users."}
            if reveal:
                body["error"] = exc.__class__.__name__
                body["message"] = str(exc)
            return Response(body, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def get_queryset(self):
        qs = User.objects.all().order_by("-date_joined")
        user = self.request.user
        probe = actor_subject_probe_for_domain_perm(user)
        if not probe:
            return qs.none()
        # Full directory: super_admin / global admin. Subject-scoped: teachers.
        if authorize(user, acc_const.PERM_MANAGE_USERS, subject=probe):
            if getattr(user, "is_superuser", False) or normalized_role(user) == acc_const.ROLE_SUPER_ADMIN:
                return _prefetch_user_directory(qs)
            if is_global_scope_staff(user) and normalized_role(user) != acc_const.ROLE_TEACHER:
                return _prefetch_user_directory(qs)
            dom = user_domain_subject(user)
            if not dom:
                raise PermissionDenied(
                    detail="A valid subject (math or english) is required to list users for this account."
                )
            clsub = (
                Classroom.SUBJECT_MATH
                if dom == acc_const.DOMAIN_MATH
                else Classroom.SUBJECT_ENGLISH
            )
            return _prefetch_user_directory(
                qs.filter(
                    Q(role=acc_const.ROLE_STUDENT)
                    & (
                        Q(access_grants__subject=dom)
                        | Q(class_memberships__classroom__subject=clsub)
                    )
                    | Q(subject=dom, role=acc_const.ROLE_TEACHER)
                ).distinct()
            )
        if authorize(user, acc_const.PERM_ASSIGN_ACCESS, subject=probe):
            if is_global_scope_staff(user) and normalized_role(user) != acc_const.ROLE_TEACHER:
                return _prefetch_user_directory(qs.filter(role=acc_const.ROLE_STUDENT))
            dom = user_domain_subject(user)
            q = Q(role=acc_const.ROLE_STUDENT)
            if not dom:
                raise PermissionDenied(
                    detail="A valid subject (math or english) is required to list users for this account."
                )
            clsub = (
                Classroom.SUBJECT_MATH
                if dom == acc_const.DOMAIN_MATH
                else Classroom.SUBJECT_ENGLISH
            )
            q &= Q(access_grants__subject=dom) | Q(class_memberships__classroom__subject=clsub)
            return _prefetch_user_directory(qs.filter(q).distinct())
        return qs.none()

class UserCreateView(generics.CreateAPIView):
    serializer_class = UserSerializer
    permission_classes = [HasManageUsers]

    def perform_create(self, serializer):
        user = serializer.save()
        actor = self.request.user
        logger.info(
            "user_created target_id=%s email=%s role=%s actor_id=%s is_superuser=%s",
            user.pk,
            user.email,
            user.role,
            getattr(actor, "pk", None),
            getattr(actor, "is_superuser", False)
            or normalized_role(actor) == acc_const.ROLE_SUPER_ADMIN,
        )


class UserUpdateView(generics.UpdateAPIView):
    serializer_class = UserSerializer
    permission_classes = [HasManageUsers]
    queryset = User.objects.all()

    def perform_update(self, serializer):
        super().perform_update(serializer)
        inst = serializer.instance
        actor = self.request.user
        logger.info(
            "user_updated target_id=%s role=%s subject=%s actor_id=%s is_superuser=%s",
            inst.pk,
            inst.role,
            getattr(inst, "subject", None),
            getattr(actor, "pk", None),
            getattr(actor, "is_superuser", False)
            or normalized_role(actor) == acc_const.ROLE_SUPER_ADMIN,
        )


class UserDeleteView(generics.DestroyAPIView):
    permission_classes = [HasManageUsers]
    queryset = User.objects.all()

    def perform_destroy(self, instance):
        actor = self.request.user
        logger.info(
            "user_deleted target_id=%s email=%s actor_id=%s is_superuser=%s",
            instance.pk,
            instance.email,
            getattr(actor, "pk", None),
            getattr(actor, "is_superuser", False)
            or normalized_role(actor) == acc_const.ROLE_SUPER_ADMIN,
        )
        super().perform_destroy(instance)

class UserRegistrationView(generics.CreateAPIView):
    serializer_class = UserSerializer
    # Truly public: stale/invalid JWT cookies must not 401 this — the /register page polls it.
    authentication_classes = []
    permission_classes = []


class UserMeView(generics.RetrieveUpdateAPIView):
    serializer_class = UserMeSerializer
    permission_classes = [IsAuthenticatedAndNotFrozen]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_object(self):
        return self.request.user


class ExamDateOptionListView(generics.ListAPIView):
    """Active exam dates for student profile dropdown."""

    permission_classes = [IsAuthenticatedAndNotFrozen]
    serializer_class = ExamDateOptionPublicSerializer

    def get_queryset(self):
        # Only upcoming dates are offered to students — past exams are filtered out.
        today = timezone.localdate()
        return (
            ExamDateOption.objects.filter(is_active=True, exam_date__gte=today)
            .order_by("sort_order", "exam_date")
        )


class ExamDateOptionAdminListCreateView(generics.ListCreateAPIView):
    permission_classes = [HasManageUsers]
    serializer_class = ExamDateOptionSerializer
    queryset = ExamDateOption.objects.all().order_by("sort_order", "exam_date")


class ExamDateOptionAdminDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [HasManageUsers]
    serializer_class = ExamDateOptionSerializer
    queryset = ExamDateOption.objects.all()


class GoogleAuthView(APIView):
    # Truly public: must not 401 on stale JWT (the /login page polls this).
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        try:
            from google.oauth2 import id_token
            from google.auth.transport import requests as google_requests
        except Exception:
            return Response(
                {"detail": "Google auth dependencies are not installed on server."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        credential = request.data.get("credential")
        if not credential:
            return Response({"detail": "Missing Google credential."}, status=status.HTTP_400_BAD_REQUEST)

        audience = settings.GOOGLE_CLIENT_ID or None
        try:
            payload = id_token.verify_oauth2_token(credential, google_requests.Request(), audience=audience)
        except Exception:
            return Response({"detail": "Invalid Google token."}, status=status.HTTP_400_BAD_REQUEST)

        email = (payload.get("email") or "").strip().lower()
        if not email:
            return Response({"detail": "Google account has no email."}, status=status.HTTP_400_BAD_REQUEST)

        if payload.get("email_verified") is False:
            return Response({"detail": "Google email is not verified."}, status=status.HTTP_400_BAD_REQUEST)

        first_name = (request.data.get("first_name") or payload.get("given_name") or "").strip()
        last_name = (request.data.get("last_name") or payload.get("family_name") or "").strip()
        username = (request.data.get("username") or "").strip()

        missing_fields = []
        if len(first_name) < 3:
            missing_fields.append("first_name")
        if len(last_name) < 3:
            missing_fields.append("last_name")

        if missing_fields:
            return Response(
                {
                    "detail": "Missing required profile fields.",
                    "missing_fields": missing_fields,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = User.objects.filter(email__iexact=email).first()
        if not user:
            if username and len(username) < 3:
                return Response({"detail": "Username must be at least 3 characters."}, status=status.HTTP_400_BAD_REQUEST)

            if not username:
                local = re.sub(r"[^a-zA-Z0-9_]", "", email.split("@")[0]) or "student"
                base = local[:30]
                candidate = base
                i = 1
                while User.objects.filter(username__iexact=candidate).exists():
                    candidate = f"{base}{i}"
                    i += 1
                username = candidate
            elif User.objects.filter(username__iexact=username).exists():
                return Response({"detail": "Username already exists."}, status=status.HTTP_400_BAD_REQUEST)

            user = User.objects.create_user(
                email=email,
                username=username,
                first_name=first_name,
                last_name=last_name,
                role=acc_const.ROLE_STUDENT,
                password=__import__("secrets").token_urlsafe(32),
            )
        else:
            updated = False
            if not user.first_name and first_name:
                user.first_name = first_name
                updated = True
            if not user.last_name and last_name:
                user.last_name = last_name
                updated = True
            if updated:
                user.save(update_fields=["first_name", "last_name"])

        clear_security_step_up(user_id=user.pk)

        refresh = RefreshToken.for_user(user)
        body = {
            "refresh": str(refresh),
            "access": str(refresh.access_token),
            "is_admin": user.is_admin,
            "role": user.role,
            "subject": _subject_for_auth_response(user),
            "is_frozen": user.is_frozen,
            "permissions": sorted(get_effective_permission_codenames(user)),
        }
        resp = Response(body, status=status.HTTP_200_OK)
        try:
            set_auth_cookies(
                response=resp,
                request=request,
                access=str(body["access"]),
                refresh=str(body["refresh"]),
                remember_me=True,
            )
            include_tokens = str(request.query_params.get("include_tokens") or "").lower() in ("1", "true", "yes")
            if not include_tokens:
                resp.data.pop("access", None)
                resp.data.pop("refresh", None)
        except Exception:
            pass
        return resp


class TelegramWidgetConfigView(APIView):
    """Public: tells the frontend whether Telegram OIDC login is configured and
    exposes the ``client_id`` (== Telegram bot id) and ``start_url`` for the OAuth flow.

    Truly public — must not 401 on stale cookies (the /login page polls this and an old
    JWT cookie would otherwise put the page into a refresh loop).
    """

    authentication_classes = []
    permission_classes = []

    def get(self, request):
        token = getattr(settings, "TELEGRAM_BOT_TOKEN", "") or ""
        if not token:
            return Response({"enabled": False, "bot_username": None, "client_id": None, "start_url": None})
        client_id = _telegram_oidc_client_id()
        client_secret = _telegram_oidc_client_secret()
        if not client_id:
            return Response({"enabled": False, "bot_username": None, "client_id": None, "start_url": None})
        username = _effective_telegram_bot_username()
        # If the client_secret + redirect_uri are configured, server-mediated OAuth is available.
        start_url = "/api/users/telegram/start/" if (client_secret and _telegram_oidc_redirect_uri()) else None
        return Response({
            "enabled": True,
            "bot_username": username or None,
            "client_id": client_id,
            "start_url": start_url,
        })


class TelegramLinkView(APIView):
    """Link Telegram to the currently logged-in account (profile «Connect Telegram»).
    Accepts ``{id_token}`` from the new OIDC SDK."""

    permission_classes = [IsAuthenticatedAndNotFrozen]

    def post(self, request):
        claims, err = _verified_telegram_oidc_payload(request.data)
        if err is not None:
            return err
        try:
            tg_id = telegram_user_id_from_claims(claims)
        except TelegramOIDCError:
            return Response({"detail": "Invalid Telegram user id."}, status=status.HTTP_400_BAD_REQUEST)

        domain = getattr(settings, "TELEGRAM_SYNTHETIC_EMAIL_DOMAIN", "telegram.mastersat.local")
        synthetic = f"tg{tg_id}@{domain}".lower()
        if User.objects.filter(Q(telegram_id=tg_id) | Q(email__iexact=synthetic)).exclude(pk=request.user.pk).exists():
            return Response(
                {"detail": "This Telegram account is already linked to another user."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        user = request.user
        if user.telegram_id is not None and user.telegram_id != tg_id:
            return Response(
                {"detail": "Your account is already linked to a different Telegram account."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        phone_err = _apply_telegram_phone_from_claims(user, claims)
        if phone_err is not None:
            return phone_err
        user.telegram_id = tg_id
        user.save(update_fields=["telegram_id"])
        return Response(UserMeSerializer(user, context={"request": request}).data, status=status.HTTP_200_OK)


class TelegramAuthView(APIView):
    """Telegram OIDC login: verify ``id_token`` (oauth.telegram.org JWT), upsert user, issue JWT cookies."""

    # Truly public: must not 401 on stale JWT — same reason as the other auth-entry endpoints.
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        # New OIDC path: verify the id_token signed by oauth.telegram.org against JWKS.
        claims, err = _verified_telegram_oidc_payload(request.data)
        if err is not None:
            return err

        try:
            tg_id = telegram_user_id_from_claims(claims)
        except TelegramOIDCError:
            return Response({"detail": "Invalid Telegram user id."}, status=status.HTTP_400_BAD_REQUEST)

        domain = getattr(settings, "TELEGRAM_SYNTHETIC_EMAIL_DOMAIN", "telegram.mastersat.local")
        email = f"tg{tg_id}@{domain}".lower()

        # OIDC claims: "name" is the display name, "preferred_username" is the @handle.
        raw_name = (str(claims.get("name") or "")).strip()
        if " " in raw_name:
            raw_fn, raw_ln = raw_name.split(" ", 1)
            raw_fn, raw_ln = raw_fn.strip(), raw_ln.strip()
        else:
            raw_fn, raw_ln = raw_name, ""
        first_name = raw_fn if len(raw_fn) >= 3 else "Telegram"
        last_name = raw_ln if len(raw_ln) >= 3 else (first_name if len(first_name) >= 3 else "User")
        if len(last_name) < 3:
            last_name = "User"

        tg_username = (str(claims.get("preferred_username") or "")).strip()
        username = (request.data.get("username") or "").strip()
        if username and len(username) < 3:
            return Response({"detail": "Username must be at least 3 characters."}, status=status.HTTP_400_BAD_REQUEST)

        user = User.objects.filter(email__iexact=email).first()
        if not user:
            if not username:
                if tg_username and len(tg_username) >= 3:
                    candidate = tg_username[:30]
                else:
                    base = f"tg{tg_id}"[:25]
                    candidate = base
                    i = 1
                    while User.objects.filter(username__iexact=candidate).exists():
                        suffix = str(i)
                        candidate = (base[: max(1, 30 - len(suffix))] + suffix)[:30]
                        i += 1
                username = candidate
            elif User.objects.filter(username__iexact=username).exists():
                return Response({"detail": "Username already exists."}, status=status.HTTP_400_BAD_REQUEST)

            user = User.objects.create_user(
                email=email,
                username=username,
                first_name=first_name,
                last_name=last_name,
                role=acc_const.ROLE_STUDENT,
                password=__import__("secrets").token_urlsafe(32),
            )
        else:
            updated = False
            if not user.first_name.strip() and raw_fn and len(raw_fn) >= 3:
                user.first_name = raw_fn
                updated = True
            if not user.last_name.strip() and raw_ln and len(raw_ln) >= 3:
                user.last_name = raw_ln
                updated = True
            if updated:
                user.save(update_fields=["first_name", "last_name"])

        phone_err = _apply_telegram_phone_from_claims(user, claims)
        if phone_err is not None:
            return phone_err
        user.telegram_id = tg_id
        user.save(update_fields=["telegram_id"])

        clear_security_step_up(user_id=user.pk)

        refresh = RefreshToken.for_user(user)
        body = {
            "refresh": str(refresh),
            "access": str(refresh.access_token),
            "is_admin": user.is_admin,
            "role": user.role,
            "subject": _subject_for_auth_response(user),
            "is_frozen": user.is_frozen,
            "permissions": sorted(get_effective_permission_codenames(user)),
        }
        resp = Response(body, status=status.HTTP_200_OK)
        try:
            set_auth_cookies(
                response=resp,
                request=request,
                access=str(body["access"]),
                refresh=str(body["refresh"]),
                remember_me=True,
            )
            include_tokens = str(request.query_params.get("include_tokens") or "").lower() in ("1", "true", "yes")
            if not include_tokens:
                resp.data.pop("access", None)
                resp.data.pop("refresh", None)
        except Exception:
            pass
        return resp


# ─── Telegram OIDC authorization-code flow (server-mediated) ──────────────────

_TELEGRAM_OAUTH_STATE_COOKIE = "tg_oauth_state"
_TELEGRAM_OAUTH_STATE_TTL_S = 300  # 5 minutes


def _upsert_user_from_telegram_claims(claims, request):
    """Shared logic for TelegramAuthView.post and TelegramOAuthCallbackView.get.

    Returns (user, None) on success or (None, error_response) on failure.
    """
    try:
        tg_id = telegram_user_id_from_claims(claims)
    except TelegramOIDCError:
        return None, Response({"detail": "Invalid Telegram user id."}, status=status.HTTP_400_BAD_REQUEST)

    domain = getattr(settings, "TELEGRAM_SYNTHETIC_EMAIL_DOMAIN", "telegram.mastersat.local")
    email = f"tg{tg_id}@{domain}".lower()

    raw_name = (str(claims.get("name") or "")).strip()
    if " " in raw_name:
        raw_fn, raw_ln = raw_name.split(" ", 1)
        raw_fn, raw_ln = raw_fn.strip(), raw_ln.strip()
    else:
        raw_fn, raw_ln = raw_name, ""
    first_name = raw_fn if len(raw_fn) >= 3 else "Telegram"
    last_name = raw_ln if len(raw_ln) >= 3 else (first_name if len(first_name) >= 3 else "User")
    if len(last_name) < 3:
        last_name = "User"

    tg_username = (str(claims.get("preferred_username") or "")).strip()
    user = User.objects.filter(telegram_id=tg_id).first() or User.objects.filter(email__iexact=email).first()
    if not user:
        if tg_username and len(tg_username) >= 3:
            base = tg_username[:30]
        else:
            base = f"tg{tg_id}"[:25]
        candidate = base
        i = 1
        while User.objects.filter(username__iexact=candidate).exists():
            suffix = str(i)
            candidate = (base[: max(1, 30 - len(suffix))] + suffix)[:30]
            i += 1
        user = User.objects.create_user(
            email=email,
            username=candidate,
            first_name=first_name,
            last_name=last_name,
            role=acc_const.ROLE_STUDENT,
            password=__import__("secrets").token_urlsafe(32),
        )
    else:
        updated = False
        if not user.first_name.strip() and raw_fn and len(raw_fn) >= 3:
            user.first_name = raw_fn
            updated = True
        if not user.last_name.strip() and raw_ln and len(raw_ln) >= 3:
            user.last_name = raw_ln
            updated = True
        if updated:
            user.save(update_fields=["first_name", "last_name"])

    phone_err = _apply_telegram_phone_from_claims(user, claims)
    if phone_err is not None:
        return None, phone_err
    user.telegram_id = tg_id
    user.save(update_fields=["telegram_id"])
    clear_security_step_up(user_id=user.pk)
    return user, None


class TelegramOAuthStartView(APIView):
    """Server-mediated OIDC start: redirect the browser to oauth.telegram.org with our client_id.

    If the request is already authenticated, the current user's id is embedded into the
    short-lived state cookie. The callback will then *link* Telegram to that account
    instead of creating a brand-new synthetic ``tg<id>@…`` user.
    """

    # Truly public — do not let a stale/invalid JWT cookie 401 the start endpoint.
    # The view soft-detects an authenticated user below via try/except so that anonymous
    # browsers still get redirected to Telegram without an error.
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        client_id = _telegram_oidc_client_id()
        client_secret = _telegram_oidc_client_secret()
        redirect_uri = _telegram_oidc_redirect_uri()
        if not (client_id and client_secret and redirect_uri):
            return Response(
                {"detail": "Telegram OIDC is not configured on the server."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        import secrets as _secrets
        from django.core import signing

        state = _secrets.token_urlsafe(24)
        nonce = _secrets.token_urlsafe(24)
        next_path = request.GET.get("next") or "/"
        if not isinstance(next_path, str) or not next_path.startswith("/") or next_path.startswith("//"):
            next_path = "/"

        # Soft-detect an existing session WITHOUT raising on invalid cookies.
        # If valid → link mode (attach Telegram to that user).
        # If invalid/missing → login mode (find/create via Telegram id).
        link_user_id = None
        try:
            auth_result = CookieOrHeaderJWTAuthentication().authenticate(request)
            if auth_result is not None:
                u, _ = auth_result
                if u is not None and getattr(u, "is_authenticated", False):
                    link_user_id = int(u.pk)
        except Exception:
            link_user_id = None

        url = build_authorize_url(
            client_id=client_id,
            redirect_uri=redirect_uri,
            state=state,
            nonce=nonce,
        )
        resp = HttpResponseRedirect(url)
        # Signed payload so the callback can trust link_user_id (and detect tampering).
        signed = signing.dumps(
            {"s": state, "n": nonce, "next": next_path, "link_user_id": link_user_id},
            salt="telegram-oauth",
        )
        resp.set_cookie(
            _TELEGRAM_OAUTH_STATE_COOKIE,
            signed,
            max_age=_TELEGRAM_OAUTH_STATE_TTL_S,
            httponly=True,
            secure=not settings.DEBUG,
            samesite="Lax",
            path="/",
        )
        return resp


class TelegramOAuthCallbackView(APIView):
    """Server-mediated OIDC callback: exchange code → id_token, upsert user, set JWT cookies, redirect."""

    authentication_classes = []
    permission_classes = []

    def get(self, request):
        from django.core import signing

        cookie_val = request.COOKIES.get(_TELEGRAM_OAUTH_STATE_COOKIE) or ""
        try:
            saved = signing.loads(cookie_val, salt="telegram-oauth", max_age=_TELEGRAM_OAUTH_STATE_TTL_S) if cookie_val else {}
        except signing.BadSignature:
            saved = {}
        except Exception:
            saved = {}
        saved_state = str(saved.get("s") or "")
        next_path = saved.get("next") or "/"
        link_user_id = saved.get("link_user_id")
        if not isinstance(next_path, str) or not next_path.startswith("/") or next_path.startswith("//"):
            next_path = "/"

        if request.GET.get("error"):
            err_resp = HttpResponseRedirect(f"/login?tg_error={request.GET.get('error')}")
            err_resp.delete_cookie(_TELEGRAM_OAUTH_STATE_COOKIE, path="/")
            return err_resp

        got_state = str(request.GET.get("state") or "")
        code = str(request.GET.get("code") or "")
        if not got_state or not saved_state or got_state != saved_state:
            err_resp = HttpResponseRedirect("/login?tg_error=state_mismatch")
            err_resp.delete_cookie(_TELEGRAM_OAUTH_STATE_COOKIE, path="/")
            return err_resp
        if not code:
            err_resp = HttpResponseRedirect("/login?tg_error=missing_code")
            err_resp.delete_cookie(_TELEGRAM_OAUTH_STATE_COOKIE, path="/")
            return err_resp

        client_id = _telegram_oidc_client_id()
        client_secret = _telegram_oidc_client_secret()
        redirect_uri = _telegram_oidc_redirect_uri()
        if not (client_id and client_secret and redirect_uri):
            err_resp = HttpResponseRedirect("/login?tg_error=server_misconfigured")
            err_resp.delete_cookie(_TELEGRAM_OAUTH_STATE_COOKIE, path="/")
            return err_resp

        try:
            tokens = exchange_code_for_tokens(
                code=code,
                client_id=client_id,
                client_secret=client_secret,
                redirect_uri=redirect_uri,
            )
            claims = verify_telegram_id_token(
                str(tokens.get("id_token") or ""),
                expected_audience=client_id,
            )
        except TelegramOIDCError as exc:
            logger.warning("telegram_oidc_callback_failed reason=%s", str(exc)[:200])
            err_resp = HttpResponseRedirect("/login?tg_error=token_exchange_failed")
            err_resp.delete_cookie(_TELEGRAM_OAUTH_STATE_COOKIE, path="/")
            return err_resp

        # Link mode: started while already authenticated → attach Telegram to existing account
        # instead of creating/finding a synthetic tg-user.
        if link_user_id is not None:
            try:
                tg_id = telegram_user_id_from_claims(claims)
            except TelegramOIDCError:
                err_resp = HttpResponseRedirect("/login?tg_error=invalid_tg_id")
                err_resp.delete_cookie(_TELEGRAM_OAUTH_STATE_COOKIE, path="/")
                return err_resp

            existing_owner = User.objects.filter(telegram_id=tg_id).exclude(pk=int(link_user_id)).first()
            if existing_owner:
                err_resp = HttpResponseRedirect(f"{next_path}?tg_error=already_linked_to_another_account")
                err_resp.delete_cookie(_TELEGRAM_OAUTH_STATE_COOKIE, path="/")
                return err_resp

            user = User.objects.filter(pk=int(link_user_id)).first()
            if not user:
                err_resp = HttpResponseRedirect("/login?tg_error=session_lost")
                err_resp.delete_cookie(_TELEGRAM_OAUTH_STATE_COOKIE, path="/")
                return err_resp
            if user.telegram_id is not None and user.telegram_id != tg_id:
                err_resp = HttpResponseRedirect(f"{next_path}?tg_error=account_already_linked")
                err_resp.delete_cookie(_TELEGRAM_OAUTH_STATE_COOKIE, path="/")
                return err_resp

            phone_err = _apply_telegram_phone_from_claims(user, claims)
            # Don't bail on phone collisions in link mode — just skip phone update.
            user.telegram_id = tg_id
            user.save(update_fields=["telegram_id"])
            resp = HttpResponseRedirect(f"{next_path}?tg_linked=1")
            resp.delete_cookie(_TELEGRAM_OAUTH_STATE_COOKIE, path="/")
            return resp

        # Login mode: no current session — find or create the synthetic user.
        user, err = _upsert_user_from_telegram_claims(claims, request)
        if err is not None or user is None:
            err_resp = HttpResponseRedirect("/login?tg_error=user_upsert_failed")
            err_resp.delete_cookie(_TELEGRAM_OAUTH_STATE_COOKIE, path="/")
            return err_resp

        refresh = RefreshToken.for_user(user)
        access = str(refresh.access_token)
        refresh_str = str(refresh)

        resp = HttpResponseRedirect(next_path)
        try:
            set_auth_cookies(
                response=resp,
                request=request,
                access=access,
                refresh=refresh_str,
                remember_me=True,
            )
            jti = _jti_of_refresh(refresh_str)
            if jti:
                ip, ua = _session_fingerprint(request)
                RefreshSession.objects.update_or_create(
                    refresh_jti=jti,
                    defaults={"user": user, "revoked_at": None, "ip": ip, "user_agent": ua},
                )
        except Exception:
            pass
        resp.delete_cookie(_TELEGRAM_OAUTH_STATE_COOKIE, path="/")
        return resp
