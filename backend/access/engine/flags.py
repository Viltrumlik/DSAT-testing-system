"""
Feature flags for the access engine rollout.

All default **off** so that deploying the engine changes no production behavior.
Flags are read from Django settings (which are populated from env vars in
``config/settings.py``), so they can be flipped per-environment without a deploy
and rolled back instantly.

    ACCESS_ENGINE_DUAL_WRITE   legacy writes also mirror into ResourceAccessGrant
    ACCESS_ENGINE_READ         VisibilityService becomes the read authority
    ACCESS_ENGINE_SHADOW_READ  compute new result alongside legacy, log drift,
                               return legacy (parity signal, zero behavior change)
"""

from __future__ import annotations

from django.conf import settings


def dual_write_enabled() -> bool:
    return bool(getattr(settings, "ACCESS_ENGINE_DUAL_WRITE", False))


def read_enabled() -> bool:
    return bool(getattr(settings, "ACCESS_ENGINE_READ", False))


def shadow_read_enabled() -> bool:
    return bool(getattr(settings, "ACCESS_ENGINE_SHADOW_READ", False))
