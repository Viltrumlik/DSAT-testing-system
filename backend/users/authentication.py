from __future__ import annotations

from django.conf import settings
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication


class CookieOrHeaderJWTAuthentication(JWTAuthentication):
    """
    Accept JWT from either:
    - Authorization: Bearer <token> (non-browser clients / backward compatibility)
    - HttpOnly cookie ``lms_access`` (browser)
    """

    access_cookie_name = "lms_access"

    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        if user is None or not user.is_active:
            return user
        if not getattr(settings, "SECURITY_STEP_UP_ENFORCE_ON_JWT", False):
            return user
        try:
            until = getattr(user, "security_step_up_required_until", None)
            if until and until > timezone.now():
                raise AuthenticationFailed(
                    {
                        "detail": "Re-authentication is required for your account due to a recent security check.",
                        "code": "security_step_up",
                    }
                )
        except AuthenticationFailed:
            raise
        except Exception:
            # Missing column mid-migrate: do not block all JWT auth.
            pass
        return user

    def authenticate(self, request):
        # First try standard header-based auth.
        out = super().authenticate(request)
        if out:
            return out

        # Then try cookie-based access token (HttpOnly; sent automatically by browser).
        raw = None
        try:
            raw = request.COOKIES.get(self.access_cookie_name)
        except Exception:
            raw = None
        if not raw:
            return None

        validated = self.get_validated_token(raw)
        return self.get_user(validated), validated

