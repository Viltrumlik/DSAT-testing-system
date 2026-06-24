"""
Validation for classroom homework file uploads (size, extension, content type).
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from django.conf import settings
from django.core.exceptions import ValidationError

if TYPE_CHECKING:
    from django.core.files.uploadedfile import UploadedFile


def _allowed_extensions() -> frozenset[str]:
    return getattr(
        settings,
        "CLASSROOM_SUBMISSION_ALLOWED_FILE_EXTENSIONS",
        frozenset({".pdf"}),
    )


def max_submission_file_bytes() -> int:
    return int(getattr(settings, "CLASSROOM_SUBMISSION_MAX_FILE_BYTES", 15 * 1024 * 1024))


def validate_submission_upload(f: UploadedFile) -> None:
    """
    Raise ValidationError if upload is not allowed.
    Call before creating SubmissionFile.
    """
    name = getattr(f, "name", "") or ""
    base = os.path.basename(name)
    _, ext = os.path.splitext(base)
    ext_lower = ext.lower()

    allowed = _allowed_extensions()
    if ext_lower and ext_lower not in allowed:
        allowed_display = ", ".join(sorted(allowed))
        raise ValidationError(
            f"File type not allowed ({ext_lower or 'no extension'}). Allowed: {allowed_display}",
            code="invalid_file_type",
        )

    size = getattr(f, "size", None)
    if size is None:
        try:
            pos = f.tell()
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(pos)
        except (OSError, AttributeError):
            size = 0

    max_b = max_submission_file_bytes()
    if size > max_b:
        raise ValidationError(
            f"File too large ({size} bytes). Maximum is {max_b} bytes.",
            code="file_too_large",
        )


def validate_submission_grade(value) -> None:
    """Optional grade must fall within configured min/max (inclusive)."""
    if value is None:
        return
    from decimal import Decimal

    lo = int(getattr(settings, "CLASSROOM_SUBMISSION_GRADE_MIN", 0))
    hi = int(getattr(settings, "CLASSROOM_SUBMISSION_GRADE_MAX", 100))
    v = float(value) if not isinstance(value, Decimal) else float(value)
    if v < lo or v > hi:
        raise ValidationError(f"Grade must be between {lo} and {hi}.")
