from __future__ import annotations

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .grading_service import grade_attempt
from .models import AssessmentAttempt


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=False, retry_jitter=True)
def grade_attempt_task(self, attempt_id: int) -> dict:
    """
    Async grading with retries + failure state.
    """
    attempt_id = int(attempt_id)
    max_retries = int(getattr(settings, "ASSESSMENT_GRADING_MAX_RETRIES", 3) or 3)
    countdown = int(getattr(settings, "ASSESSMENT_GRADING_RETRY_COUNTDOWN_SECONDS", 10) or 10)
    try:
        res = grade_attempt(attempt_id=attempt_id)
        return {"attempt_id": attempt_id, "graded": bool(res), "result_id": getattr(res, "pk", None)}
    except Exception as exc:
        # Mark failure on the attempt row (best-effort).
        try:
            with transaction.atomic():
                att = AssessmentAttempt.objects.select_for_update().filter(pk=attempt_id).first()
                if att:
                    att.grading_status = AssessmentAttempt.GRADING_FAILED
                    att.grading_error = str(exc)[:4000]
                    att.grading_last_attempt_at = timezone.now()
                    att.save(update_fields=["grading_status", "grading_error", "grading_last_attempt_at"])
        except Exception:
            pass
        # Retry if budget remains; Celery will raise Retry.
        if getattr(self.request, "retries", 0) < max_retries:
            raise self.retry(exc=exc, countdown=countdown)
        raise

