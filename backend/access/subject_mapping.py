"""
Central vocabulary: **platform** vs **domain** subject strings.

Why two names
~~~~~~~~~~~~~

* **Platform subject** — values stored on exam content (``PracticeTest.subject``):
  ``MATH``, ``READING_WRITING``. This is what ``authorize(..., subject=...)`` MUST receive
  for domain-scoped permissions (see ``access.constants.PERMISSIONS_REQUIRING_PLATFORM_SUBJECT``).

* **Domain subject** — values on ``User.subject`` and ``UserAccess.subject``:
  ``math``, ``english``. Use these with ``has_global_subject_access``,
  ``has_access_for_classroom``, and ``student_has_any_subject_grant``.

Rule for contributors
~~~~~~~~~~~~~~~~~~~~~

Never pass ``math`` / ``english`` into ``authorize``. Convert at the boundary using the
functions below. Passing the wrong vocabulary raises ``access.exceptions.SubjectContractViolation``.
"""

from __future__ import annotations

from typing import Optional

from . import constants
from .exceptions import SubjectContractViolation

# Valid ``PracticeTest.subject`` / ``authorize(..., subject=...)`` values.
PLATFORM_SUBJECTS: frozenset[str] = frozenset(
    {constants.SUBJECT_MATH_PLATFORM, constants.SUBJECT_ENGLISH_PLATFORM}
)


def looks_like_domain_subject(value: object) -> bool:
    """True if ``value`` is the LMS domain vocabulary (``math`` / ``english``), case-insensitive."""
    if not isinstance(value, str):
        return False
    v = value.strip().lower()
    return v in constants.ALL_DOMAIN_SUBJECTS


def looks_like_platform_subject(value: object) -> bool:
    """True if ``value`` is exactly one of the known exam platform subjects."""
    return isinstance(value, str) and value in PLATFORM_SUBJECTS


def platform_subject_to_domain(platform_subject: Optional[str]) -> Optional[str]:
    """``MATH`` / ``READING_WRITING`` → ``math`` / ``english``. Unknown → ``None``."""
    if platform_subject == constants.SUBJECT_MATH_PLATFORM:
        return constants.DOMAIN_MATH
    if platform_subject == constants.SUBJECT_ENGLISH_PLATFORM:
        return constants.DOMAIN_ENGLISH
    return None


def domain_subject_to_platform(domain: Optional[str]) -> Optional[str]:
    """``math`` / ``english`` → ``MATH`` / ``READING_WRITING``. Unknown / empty → ``None``."""
    if domain == constants.DOMAIN_MATH:
        return constants.SUBJECT_MATH_PLATFORM
    if domain == constants.DOMAIN_ENGLISH:
        return constants.SUBJECT_ENGLISH_PLATFORM
    return None


def validate_authorize_subject(subject: str) -> None:
    """
    ``authorize(..., subject=...)`` must receive a **platform** string.

    Raises ``SubjectContractViolation`` on programmer error; does nothing for valid values.
    """
    if not isinstance(subject, str) or not subject.strip():
        raise SubjectContractViolation(
            "authorize(..., subject=...) received an empty subject. "
            "Use constants.SUBJECT_MATH_PLATFORM, constants.SUBJECT_ENGLISH_PLATFORM, "
            "or subject_mapping.domain_subject_to_platform(domain)."
        )
    s = subject.strip()
    # Accept platform subjects case-insensitively (canonicalize to uppercase for checks).
    # IMPORTANT: check platform first, otherwise "MATH" lowercases to "math" and looks like a domain subject.
    s_upper = s.upper()
    if s_upper in PLATFORM_SUBJECTS:
        return
    if looks_like_domain_subject(s):
        raise SubjectContractViolation(
            f"authorize(..., subject=...) received domain subject {s!r}. "
            "Pass a platform subject (MATH or READING_WRITING). "
            "Convert with access.subject_mapping.domain_subject_to_platform('math'|'english')."
        )
    if platform_subject_to_domain(s) is None:
        raise SubjectContractViolation(
            f"authorize(..., subject=...) received unknown subject {s!r}. "
            f"Expected one of {sorted(PLATFORM_SUBJECTS)!r}."
        )


def validate_domain_subject_arg(name: str, domain_subject: str) -> None:
    """
    ``has_global_subject_access`` / ``has_access_for_classroom`` / ``student_has_any_subject_grant``
    expect **domain** strings only.
    """
    if domain_subject in PLATFORM_SUBJECTS:
        raise SubjectContractViolation(
            f"{name}() received platform subject {domain_subject!r}. "
            "Pass constants.DOMAIN_MATH or constants.DOMAIN_ENGLISH, "
            "or convert with access.subject_mapping.platform_subject_to_domain(...)."
        )
    if domain_subject not in constants.ALL_DOMAIN_SUBJECTS:
        raise SubjectContractViolation(
            f"{name}() received invalid domain subject {domain_subject!r}. "
            f"Expected one of {list(constants.ALL_DOMAIN_SUBJECTS)!r}."
        )
