"""Normalize and lightly validate phone numbers (international-friendly)."""

from __future__ import annotations

import re
from typing import Optional


def normalize_phone(value: Optional[str]) -> Optional[str]:
    """Strip spaces/dashes; return None if empty. Does not enforce uniqueness."""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    compact = re.sub(r"[\s\-.]", "", s)
    if len(compact) < 7 or len(compact) > 16:
        raise ValueError("Phone number must be between 7 and 16 characters (digits and optional leading +).")
    if not re.match(r"^\+?[0-9]+$", compact):
        raise ValueError("Phone number may only contain digits and an optional leading +.")
    return compact
