"""
Celery tasks for classroom / homework maintenance.
"""

from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger("classes.tasks")


@shared_task(name="classes.tasks.cleanup_stale_homework_storage")
def cleanup_stale_homework_storage() -> dict:
    from .stale_storage_cleanup import run_stale_storage_cleanup

    stats = run_stale_storage_cleanup()
    logger.info("cleanup_stale_homework_storage %s", stats)
    return stats


@shared_task(name="classes.tasks.prune_homework_staged_uploads")
def prune_homework_staged_uploads() -> dict:
    """Periodic deletion of old ``HomeworkStagedUpload`` attached rows (see retention setting)."""
    from .stale_storage_cleanup import prune_homework_staged_upload_records

    stats = prune_homework_staged_upload_records()
    logger.info("prune_homework_staged_uploads %s", stats)
    return stats
