import logging

from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import Question
from .question_ordering import dense_compact_module_orders_locked

logger = logging.getLogger(__name__)


@receiver(post_delete, sender=Question)
def question_normalize_after_delete(sender, instance, **kwargs):
    from django.conf import settings

    if not getattr(settings, "EXAM_QUESTION_COMPACT_ON_DELETE", False):
        return
    dense_compact_module_orders_locked(instance.module_id)
