"""
Dual-write mirroring (Stage 1 of the migration).

When ``ACCESS_ENGINE_DUAL_WRITE`` is on, legacy access writes are mirrored into
``ResourceAccessGrant`` via Django signals, so the new engine's data stays current
*before* any read cutover. When the flag is off (production default) every handler
returns immediately — zero behavior change.

**Safety:** mirroring must never break a legacy write. Every handler is wrapped so
any error is logged and swallowed; the legacy transaction proceeds regardless.
"""

from __future__ import annotations

import logging

from django.db.models.signals import m2m_changed, post_save

from access.models import ResourceAccessGrant
from . import flags

logger = logging.getLogger("access.dual_write")


def _safe(fn):
    def wrapper(*args, **kwargs):
        if not flags.dual_write_enabled():
            return
        try:
            fn(*args, **kwargs)
        except Exception:  # never break the legacy write
            logger.exception("access dual-write mirror failed in %s", getattr(fn, "__name__", fn))
    return wrapper


# -- UserAccess (subject grants) ----------------------------------------

@_safe
def _mirror_user_access(sender, instance, created, **kwargs):
    from .assignment_service import AssignmentService

    source = (
        ResourceAccessGrant.SOURCE_CLASSROOM
        if instance.classroom_id
        else ResourceAccessGrant.SOURCE_MANUAL
    )
    AssignmentService.assign_subject(
        instance.user,
        instance.subject,
        actor=getattr(instance, "granted_by", None),
        source=source,
        classroom=instance.classroom_id,
        note="dual-write mirror of access.UserAccess",
    )


# -- assigned_users M2Ms (resource grants) ------------------------------

def _mirror_m2m(resource_type, instance, pk_set, action, actor=None):
    from django.contrib.auth import get_user_model

    from .assignment_service import AssignmentService

    User = get_user_model()
    if action == "post_add" and pk_set:
        users = list(User.objects.filter(pk__in=pk_set))
        AssignmentService.bulk_assign_resource(
            users, resource_type, instance.pk,
            source=ResourceAccessGrant.SOURCE_BULK,
            note="dual-write mirror of assigned_users",
            require_exists=False,
        )
    elif action in ("post_remove", "post_clear") and pk_set:
        for uid in pk_set:
            AssignmentService.revoke_resource(
                User(pk=uid), resource_type, instance.pk,
                note="dual-write mirror of assigned_users remove",
            )


@_safe
def _mirror_practice_test_users(sender, instance, action, pk_set, reverse, **kwargs):
    from access import resources

    if reverse or action not in ("post_add", "post_remove", "post_clear"):
        return
    _mirror_m2m(resources.RT_PRACTICE_TEST, instance, pk_set, action)


@_safe
def _mirror_mock_exam_users(sender, instance, action, pk_set, reverse, **kwargs):
    from access import resources

    if reverse or action not in ("post_add", "post_remove", "post_clear"):
        return
    _mirror_m2m(resources.RT_MOCK_EXAM, instance, pk_set, action)


@_safe
def _mirror_portal_mock_users(sender, instance, action, pk_set, reverse, **kwargs):
    """PortalMockExam mirrors onto its underlying MockExam resource id."""
    from access import resources

    if reverse or action not in ("post_add", "post_remove", "post_clear"):
        return
    mock_id = getattr(instance, "mock_exam_id", None)
    if not mock_id:
        return

    class _Shim:
        pk = mock_id

    _mirror_m2m(resources.RT_MOCK_EXAM, _Shim(), pk_set, action)


def connect() -> None:
    """Wire signal receivers. Called from AccessConfig.ready(). Idempotent (dispatch_uid)."""
    from exams.models import MockExam, PortalMockExam, PracticeTest
    from access.models import UserAccess

    post_save.connect(
        _mirror_user_access, sender=UserAccess,
        dispatch_uid="access_dualwrite_useraccess",
    )
    m2m_changed.connect(
        _mirror_practice_test_users, sender=PracticeTest.assigned_users.through,
        dispatch_uid="access_dualwrite_pt_users",
    )
    m2m_changed.connect(
        _mirror_mock_exam_users, sender=MockExam.assigned_users.through,
        dispatch_uid="access_dualwrite_mock_users",
    )
    m2m_changed.connect(
        _mirror_portal_mock_users, sender=PortalMockExam.assigned_users.through,
        dispatch_uid="access_dualwrite_portal_users",
    )
