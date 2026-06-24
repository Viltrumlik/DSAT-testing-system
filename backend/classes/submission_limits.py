"""
Submission upload limits: file count, batch size, and throttling helpers.
"""

from __future__ import annotations

from django.conf import settings


def max_files_per_submission() -> int:
    return int(getattr(settings, "CLASSROOM_SUBMISSION_MAX_FILES_PER_SUBMISSION", 50))


def max_batch_upload_bytes() -> int:
    """Max total size of *new* files in one submit request (multipart batch)."""
    return int(getattr(settings, "CLASSROOM_SUBMISSION_MAX_BATCH_BYTES", 100 * 1024 * 1024))
