"""
Create and prune ``ClassroomStreamItem`` rows when posts, assignments, or submissions change.

Does not alter core domain models — stream is a derived, denormalized feed layer.
"""

from __future__ import annotations

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import Assignment, ClassComment, ClassPost, ClassroomStreamItem, Submission
from realtime.services import emit_to_classroom_members, emit_to_user


def _ensure_stream_post(post: ClassPost) -> None:
    item, _ = ClassroomStreamItem.objects.update_or_create(
        stream_type=ClassroomStreamItem.TYPE_POST,
        related_id=post.pk,
        defaults={
            "classroom_id": post.classroom_id,
            "actor_id": post.author_id,
        },
    )
    emit_to_classroom_members(
        classroom_id=post.classroom_id,
        event_type="stream.updated",
        payload={"classroom_id": post.classroom_id, "item_id": item.id, "reason": "post"},
    )


def _ensure_stream_assignment(assignment: Assignment) -> None:
    item, _ = ClassroomStreamItem.objects.update_or_create(
        stream_type=ClassroomStreamItem.TYPE_ASSIGNMENT,
        related_id=assignment.pk,
        defaults={
            "classroom_id": assignment.classroom_id,
            "actor_id": assignment.created_by_id,
        },
    )
    emit_to_classroom_members(
        classroom_id=assignment.classroom_id,
        event_type="stream.updated",
        payload={
            "classroom_id": assignment.classroom_id,
            "item_id": item.id,
            "reason": "assignment_created",
            "assignment_id": assignment.pk,
        },
    )


def _ensure_stream_submission(submission: Submission) -> None:
    if submission.status != Submission.STATUS_SUBMITTED:
        return
    item, _ = ClassroomStreamItem.objects.update_or_create(
        stream_type=ClassroomStreamItem.TYPE_SUBMISSION,
        related_id=submission.pk,
        defaults={
            "classroom_id": submission.assignment.classroom_id,
            "actor_id": submission.student_id,
        },
    )
    classroom_id = submission.assignment.classroom_id
    emit_to_classroom_members(
        classroom_id=classroom_id,
        event_type="stream.updated",
        payload={
            "classroom_id": classroom_id,
            "item_id": item.id,
            "reason": "submission",
            "submission_id": submission.pk,
        },
        roles=("ADMIN",),
    )
    emit_to_user(
        user_id=submission.student_id,
        event_type="workspace.updated",
        payload={"classroom_id": classroom_id, "reason": "submission", "submission_id": submission.pk},
    )


@receiver(post_save, sender=ClassPost)
def stream_on_post_save(sender, instance: ClassPost, created, **kwargs):
    _ensure_stream_post(instance)


@receiver(post_save, sender=Assignment)
def stream_on_assignment_save(sender, instance: Assignment, created, **kwargs):
    if created:
        _ensure_stream_assignment(instance)


@receiver(post_save, sender=Submission)
def stream_on_submission_save(sender, instance: Submission, **kwargs):
    _ensure_stream_submission(instance)


@receiver(post_delete, sender=ClassPost)
def stream_on_post_delete(sender, instance: ClassPost, **kwargs):
    ClassroomStreamItem.objects.filter(
        stream_type=ClassroomStreamItem.TYPE_POST,
        related_id=instance.pk,
    ).delete()


@receiver(post_delete, sender=Assignment)
def stream_on_assignment_delete(sender, instance: Assignment, **kwargs):
    ClassroomStreamItem.objects.filter(
        stream_type=ClassroomStreamItem.TYPE_ASSIGNMENT,
        related_id=instance.pk,
    ).delete()
    ClassComment.objects.filter(
        target_type=ClassComment.TARGET_ASSIGNMENT,
        target_id=instance.pk,
    ).delete()


@receiver(post_delete, sender=Submission)
def stream_on_submission_delete(sender, instance: Submission, **kwargs):
    ClassroomStreamItem.objects.filter(
        stream_type=ClassroomStreamItem.TYPE_SUBMISSION,
        related_id=instance.pk,
    ).delete()


@receiver(post_delete, sender=ClassPost)
def comments_on_post_delete(sender, instance: ClassPost, **kwargs):
    ClassComment.objects.filter(
        target_type=ClassComment.TARGET_POST,
        target_id=instance.pk,
    ).delete()


