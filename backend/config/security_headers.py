from __future__ import annotations

import os
from secrets import token_urlsafe


def _env_bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return str(v).lower() in ("1", "true", "yes", "on")


class CSPMiddleware:
    """
    Content-Security-Policy with a safe rollout:

    - Default: Report-Only in production (set CSP_ENFORCE=true to enforce).
    - Strict mode: set CSP_STRICT=true to remove 'unsafe-inline' from script-src.
      (May require Next.js nonce work; roll out after verifying.)
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.enforce = _env_bool("CSP_ENFORCE", default=False)
        self.strict = _env_bool("CSP_STRICT", default=False)
        self.csp_reporting = _env_bool("CSP_ENABLE_REPORTING", default=True)
        self.csp_report_path = os.getenv("CSP_REPORT_PATH", "/api/csp-report/").strip() or "/api/csp-report/"

    def __call__(self, request):
        response = self.get_response(request)

        # Only for HTML/doc + API responses (browsers).
        nonce = token_urlsafe(16)
        setattr(request, "csp_nonce", nonce)

        script_src = ["'self'"]
        style_src = ["'self'", "'unsafe-inline'"]  # Tailwind/inline styles in UI
        if not self.strict:
            script_src.append("'unsafe-inline'")

        # Note: connect-src includes same-origin; add wss if needed.
        policy = {
            "default-src": ["'self'"],
            "base-uri": ["'self'"],
            "object-src": ["'none'"],
            "frame-ancestors": ["'none'"],
            "img-src": ["'self'", "data:", "blob:"],
            "font-src": ["'self'", "data:"],
            "media-src": ["'self'", "blob:"],
            "connect-src": ["'self'"],
            "script-src": script_src,
            "style-src": style_src,
        }
        if self.csp_reporting:
            # Collect violations during report-only; disable with CSP_ENABLE_REPORTING=false in edge cases.
            policy["report-uri"] = [self.csp_report_path]

        header_value = "; ".join(f"{k} {' '.join(v)}" for k, v in policy.items())
        header_name = "Content-Security-Policy" if self.enforce else "Content-Security-Policy-Report-Only"
        response.headers[header_name] = header_value

        return response

