"""Verify Telegram OIDC id_token (https://core.telegram.org/bots/telegram-login).

Replaces the legacy HMAC widget. Telegram now issues an OpenID Connect JWT signed
by oauth.telegram.org. We fetch the JWKS once (with TTL), then verify signature,
issuer, audience, and expiry.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, Mapping, Optional

import jwt
import requests

logger = logging.getLogger(__name__)

OIDC_ISSUER = "https://oauth.telegram.org"
OIDC_AUTHORIZE_URL = "https://oauth.telegram.org/auth"
OIDC_TOKEN_URL = "https://oauth.telegram.org/token"
JWKS_URL = "https://oauth.telegram.org/.well-known/jwks.json"
JWKS_TTL_SECONDS = 600  # refresh signing keys every 10 minutes
SUPPORTED_ALGS = ("RS256", "ES256", "EdDSA", "ES256K")

_jwks_cache_lock = threading.Lock()
_jwks_cache: Dict[str, Any] = {"keys": None, "fetched_at": 0.0}


class TelegramOIDCError(Exception):
    """Raised when an id_token cannot be verified."""


def _fetch_jwks(force: bool = False) -> Dict[str, Any]:
    now = time.time()
    with _jwks_cache_lock:
        if not force and _jwks_cache["keys"] is not None and (now - _jwks_cache["fetched_at"]) < JWKS_TTL_SECONDS:
            return _jwks_cache["keys"]
    # Network call outside the lock to avoid head-of-line blocking.
    resp = requests.get(JWKS_URL, timeout=5)
    resp.raise_for_status()
    body = resp.json()
    with _jwks_cache_lock:
        _jwks_cache["keys"] = body
        _jwks_cache["fetched_at"] = time.time()
    return body


def verify_telegram_id_token(
    id_token: str,
    *,
    expected_audience: str,
    leeway_seconds: int = 30,
) -> Mapping[str, Any]:
    """Verify a Telegram-issued id_token. Returns the decoded claims on success.

    Raises ``TelegramOIDCError`` for any failure (bad signature, wrong issuer/audience,
    expired). The caller is responsible for treating the result as authenticated user
    data and only trusting it after this returns successfully.
    """
    if not id_token or not isinstance(id_token, str):
        raise TelegramOIDCError("Missing id_token.")
    if not expected_audience:
        raise TelegramOIDCError("Server is missing Telegram client id (audience).")

    try:
        unverified_header = jwt.get_unverified_header(id_token)
    except jwt.PyJWTError as exc:
        raise TelegramOIDCError(f"Malformed id_token header: {exc}") from exc

    kid = unverified_header.get("kid")
    if not kid:
        raise TelegramOIDCError("id_token header missing 'kid'.")

    # Try cached JWKS first; if kid not found, force-refresh once (key rotation).
    for attempt in (False, True):
        try:
            jwks = _fetch_jwks(force=attempt)
        except (requests.RequestException, ValueError) as exc:
            raise TelegramOIDCError(f"JWKS fetch failed: {exc}") from exc

        signing_key: Optional[Any] = None
        for key in jwks.get("keys", []):
            if key.get("kid") == kid:
                try:
                    signing_key = jwt.algorithms.get_default_algorithms()[key["alg"]].from_jwk(key)
                except (KeyError, ValueError, jwt.PyJWTError) as exc:
                    raise TelegramOIDCError(f"Cannot load JWK kid={kid}: {exc}") from exc
                break
        if signing_key is not None:
            break
    else:
        signing_key = None

    if signing_key is None:
        raise TelegramOIDCError(f"No matching signing key for kid={kid}.")

    try:
        claims = jwt.decode(
            id_token,
            key=signing_key,
            algorithms=list(SUPPORTED_ALGS),
            audience=str(expected_audience),
            issuer=OIDC_ISSUER,
            leeway=leeway_seconds,
            options={"require": ["exp", "iat", "iss", "sub", "aud"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise TelegramOIDCError("id_token expired.") from exc
    except jwt.InvalidAudienceError as exc:
        raise TelegramOIDCError("id_token audience mismatch.") from exc
    except jwt.InvalidIssuerError as exc:
        raise TelegramOIDCError("id_token issuer mismatch.") from exc
    except jwt.PyJWTError as exc:
        raise TelegramOIDCError(f"id_token verification failed: {exc}") from exc

    return claims


def build_authorize_url(
    *,
    client_id: str,
    redirect_uri: str,
    state: str,
    nonce: str,
    scope: str = "openid profile phone",
) -> str:
    """Construct the Telegram OIDC ``/auth`` redirect URL for the authorization-code flow."""
    from urllib.parse import urlencode

    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": scope,
        "state": state,
        "nonce": nonce,
    }
    return f"{OIDC_AUTHORIZE_URL}?{urlencode(params)}"


def exchange_code_for_tokens(
    *,
    code: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
) -> Mapping[str, Any]:
    """POST to Telegram's token endpoint to exchange an auth code for tokens.

    Returns the JSON body on success. Raises ``TelegramOIDCError`` for HTTP / parse errors.
    The result is expected to include ``id_token`` (JWT) which must still be verified
    via ``verify_telegram_id_token``.
    """
    if not code or not client_id or not client_secret or not redirect_uri:
        raise TelegramOIDCError("Token exchange missing required parameters.")
    try:
        resp = requests.post(
            OIDC_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
            },
            headers={"Accept": "application/json"},
            timeout=10,
        )
    except requests.RequestException as exc:
        raise TelegramOIDCError(f"Token exchange network error: {exc}") from exc
    if resp.status_code != 200:
        # Telegram returns OAuth-style error JSON. Surface it for debugging without leaking secrets.
        body_preview = (resp.text or "")[:300]
        raise TelegramOIDCError(
            f"Token exchange failed: HTTP {resp.status_code}: {body_preview}"
        )
    try:
        body = resp.json()
    except ValueError as exc:
        raise TelegramOIDCError(f"Token endpoint returned non-JSON: {exc}") from exc
    if not isinstance(body, dict) or "id_token" not in body:
        raise TelegramOIDCError("Token endpoint response missing id_token.")
    return body


_BIGINT_MAX = (1 << 63) - 1  # PostgreSQL bigint max (signed 64-bit)


def telegram_user_id_from_claims(claims: Mapping[str, Any]) -> int:
    """Extract a stable, bigint-safe user id from verified OIDC claims.

    Telegram's ``sub`` is documented as a numeric Telegram user id, but in OIDC
    responses it sometimes arrives as a very large opaque identifier that exceeds
    PostgreSQL's signed bigint range (2**63-1 ≈ 9.22×10^18). To keep the existing
    ``users.telegram_id`` column (bigint) we hash any out-of-range value down to a
    stable 63-bit fingerprint. Same sub always maps to the same id.
    """
    import hashlib

    sub = claims.get("sub")
    if sub is None:
        raise TelegramOIDCError("Verified claims missing 'sub'.")
    sub_str = str(sub)
    try:
        raw = int(sub_str)
    except (TypeError, ValueError) as exc:
        raise TelegramOIDCError(f"Invalid 'sub' value: {sub!r}") from exc
    if 0 < raw <= _BIGINT_MAX:
        return raw
    # Out of bigint range (rare) — derive a stable 63-bit positive hash.
    digest = hashlib.sha256(sub_str.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") & _BIGINT_MAX
