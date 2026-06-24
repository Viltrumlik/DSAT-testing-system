from django.db.models.signals import post_save
from django.dispatch import receiver

from exams.models import TestAttempt

from .homework_auto_submit import sync_homework_after_test_attempt_saved


@receiver(post_save, sender=TestAttempt)
def classroom_homework_sync_on_test_attempt_save(sender, instance, **kwargs):
    sync_homework_after_test_attempt_saved(instance)
