"""
Safe deletion of homework submission files from storage with retries.

On persistent failure, record a row for operators (or a future cleanup job).
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django.db.models.fields.files import FieldFile

logger = logging.getLogger("classes.submission_file_storage")

# Exponential backoff between attempts (seconds).
_BACKOFF = (0.02, 0.08, 0.24)


def delete_submission_file_storage(filefield: FieldFile | None, *, max_attempts: int = 3) -> bool:
    """
    Delete the underlying storage object for a FileField. Returns True if deleted or nothing to delete.
    Returns False only if all attempts failed (caller may queue stale blob cleanup).
    """
    if not filefield or not getattr(filefield, "name", None):
        return True
    name = filefield.name
    for i in range(max_attempts):
        try:
            filefield.delete(save=False)
            return True
        except Exception as e:
            logger.warning(
                "submission_file_storage_delete_attempt name=%s attempt=%s/%s err=%s",
                name,
                i + 1,
                max_attempts,
                e,
            )
            if i + 1 < max_attempts:
                time.sleep(_BACKOFF[min(i, len(_BACKOFF) - 1)])
    return False


def record_stale_storage_blob(storage_name: str, reason: str = "") -> None:
    """Persist a path for later retry or manual cleanup (does not raise)."""
    try:
        from .models import StaleStorageBlob

        StaleStorageBlob.objects.create(storage_name=storage_name[:512], reason=reason[:2000])
    except Exception:
        logger.exception("record_stale_storage_blob_failed name=%s", storage_name)
