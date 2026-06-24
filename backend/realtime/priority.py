"""Priority helpers for channels and ordering."""

from __future__ import annotations

from .constants import PRIORITY_HIGH, PRIORITY_LOW, PRIORITY_MEDIUM

_PRIORITY_TO_CODE = {
    PRIORITY_HIGH: "h",
    PRIORITY_MEDIUM: "m",
    PRIORITY_LOW: "l",
}

_ORDER = {PRIORITY_HIGH: 0, PRIORITY_MEDIUM: 1, PRIORITY_LOW: 2}


def priority_code(priority: str) -> str:
    return _PRIORITY_TO_CODE.get(str(priority), "m")


def priority_sort_key(priority: str) -> int:
    return _ORDER.get(str(priority), 1)
