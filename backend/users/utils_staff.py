"""Django `is_staff`: only Django superusers and SUPER_ADMIN role (LMS) may use /django-admin/."""

from __future__ import annotations

from access import constants


def sync_django_staff_flag(user) -> None:
    from django.contrib.auth import get_user_model

    User = get_user_model()
    if getattr(user, "is_superuser", False):
        User.objects.filter(pk=user.pk).update(is_staff=True)
        return
    if user.role == constants.ROLE_SUPER_ADMIN:
        User.objects.filter(pk=user.pk).update(is_staff=True)
    else:
        User.objects.filter(pk=user.pk).update(is_staff=False)
