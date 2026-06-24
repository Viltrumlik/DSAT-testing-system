from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def report_error(kind: str, *, exc: Exception | None = None, context: dict[str, Any] | None = None) -> None:
    """
    Pluggable error reporting hook (non-Sentry).
    Default behavior: structured log line that can be shipped to your error tracker.
    """

    payload: dict[str, Any] = {"kind": str(kind)}
    if context:
        payload["context"] = context
    if exc is not None:
        payload["exc_type"] = exc.__class__.__name__
        payload["exc"] = str(exc)

    # Emit JSON so it can be ingested reliably.
    try:
        msg = json.dumps(payload, sort_keys=True, default=str)
    except Exception:
        msg = f"{payload}"

    level = os.getenv("ERROR_REPORTING_LEVEL", "error").lower()
    if level == "warning":
        logger.warning("error_report %s", msg)
    else:
        logger.error("error_report %s", msg, exc_info=exc)

