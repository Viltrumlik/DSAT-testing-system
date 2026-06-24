from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger("assessments.mitigation")


def _enabled() -> bool:
    return str(getattr(settings, "ASSESSMENT_HW_AUTO_MITIGATE", "")).lower() in ("1", "true", "yes")


def is_user_assignment_blocked(user_id: int | None) -> bool:
    if not user_id:
        return False
    try:
        return bool(cache.get(f"assess:mitigate:block:user:{int(user_id)}"))
    except Exception:
        return False


def is_classroom_mitigation_strict(classroom_id: int | None) -> bool:
    if not classroom_id:
        return False
    try:
        return bool(cache.get(f"assess:mitigate:strict:class:{int(classroom_id)}"))
    except Exception:
        return False


def apply_mitigation_for_pattern(
    pattern: dict[str, Any],
    *,
    actor_role: str | None = None,
    actor_is_global_staff: bool = False,
) -> dict[str, Any]:
    """
    Optional auto-mitigation after an abuse threshold is crossed (sliding window).

    - user_assignment_spike: temporary block on assignment endpoint for that user
    - classroom_assignment_spike: stricter per-class throttle scope (see throttles)
    - global_assignment_spike: optional short global cooldown flag (blocks all assignment posts)
    """
    out: dict[str, Any] = {"applied": []}
    if not _enabled():
        return out

    kind = pattern.get("kind")
    user_block_s = int(getattr(settings, "ASSESSMENT_HW_MITIGATE_USER_BLOCK_SECONDS", 900) or 900)
    user_block_s = max(60, min(24 * 3600, user_block_s))
    class_strict_s = int(getattr(settings, "ASSESSMENT_HW_MITIGATE_CLASS_STRICT_SECONDS", 1800) or 1800)
    class_strict_s = max(120, min(24 * 3600, class_strict_s))
    global_cooldown_s = int(getattr(settings, "ASSESSMENT_HW_MITIGATE_GLOBAL_COOLDOWN_SECONDS", 120) or 120)
    global_cooldown_s = max(30, min(3600, global_cooldown_s))

    try:
        # Trust-aware logic:
        # - Never auto-mitigate global staff (admin/test_admin/super_admin) to avoid weaponization.
        # - Only apply user mitigation to the same actor (the alert pattern must be about that user).
        if actor_is_global_staff:
            return out

        if kind == "user_assignment_spike" and pattern.get("user_id"):
            uid = int(pattern["user_id"])
            k = f"assess:mitigate:block:user:{uid}"
            cache.set(k, True, timeout=user_block_s)
            out["applied"].append({"action": "block_user_assignments", "user_id": uid, "seconds": user_block_s})

        # Classroom mitigation: only allow if the spike is attributable to a single actor context (teacher).
        if kind == "classroom_assignment_spike" and pattern.get("classroom_id") and actor_role == "teacher":
            cid = int(pattern["classroom_id"])
            k = f"assess:mitigate:strict:class:{cid}"
            cache.set(k, True, timeout=class_strict_s)
            out["applied"].append({"action": "strict_classroom_throttle", "classroom_id": cid, "seconds": class_strict_s})

        # Global mitigation is the most weaponizable; only enable for teachers and only when explicitly configured.
        if kind == "global_assignment_spike" and actor_role == "teacher" and str(
            getattr(settings, "ASSESSMENT_HW_MITIGATE_GLOBAL_BLOCK_ASSIGN", "false")
        ).lower() in ("1", "true", "yes"):
            cache.set("assess:mitigate:block:assign:global", True, timeout=global_cooldown_s)
            out["applied"].append({"action": "global_assignment_cooldown", "seconds": global_cooldown_s})
    except Exception:
        logger.exception("apply_mitigation_for_pattern failed pattern=%s", pattern)

    return out


def is_global_assignment_blocked() -> bool:
    try:
        return bool(cache.get("assess:mitigate:block:assign:global"))
    except Exception:
        return False
