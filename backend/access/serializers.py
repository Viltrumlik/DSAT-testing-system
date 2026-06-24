"""Serializers for the access-engine admin API (Phase 2 frontend)."""

from __future__ import annotations

from rest_framework import serializers

from . import resources
from .models import AccessGrantEvent, ResourceAccessGrant


def _user_label(user) -> str:
    if user is None:
        return ""
    fn = (getattr(user, "first_name", "") or "").strip()
    ln = (getattr(user, "last_name", "") or "").strip()
    name = f"{fn} {ln}".strip()
    return name or (getattr(user, "email", "") or getattr(user, "username", "") or f"#{user.pk}")


class ResourceAccessGrantSerializer(serializers.ModelSerializer):
    user_email = serializers.SerializerMethodField()
    user_name = serializers.SerializerMethodField()
    granted_by_email = serializers.SerializerMethodField()
    classroom_name = serializers.SerializerMethodField()
    is_effective = serializers.SerializerMethodField()
    resource_label = serializers.SerializerMethodField()

    class Meta:
        model = ResourceAccessGrant
        fields = (
            "id", "user", "user_email", "user_name", "scope", "subject",
            "resource_type", "resource_id", "resource_label", "classroom", "classroom_name",
            "source", "status", "is_effective", "granted_by", "granted_by_email",
            "expires_at", "created_at", "updated_at",
        )
        read_only_fields = fields

    def get_user_email(self, obj):
        return getattr(obj.user, "email", "") or getattr(obj.user, "username", "")

    def get_user_name(self, obj):
        return _user_label(obj.user)

    def get_granted_by_email(self, obj):
        return getattr(obj.granted_by, "email", "") if obj.granted_by_id else ""

    def get_classroom_name(self, obj):
        return getattr(obj.classroom, "name", "") if obj.classroom_id else ""

    def get_is_effective(self, obj):
        return obj.is_effective()

    def get_resource_label(self, obj):
        # Subject grants have no concrete resource; show the subject instead.
        if obj.scope != ResourceAccessGrant.SCOPE_RESOURCE or not obj.resource_type:
            return ""
        return resources.label_for(obj.resource_type, obj.resource_id)


class AccessGrantEventSerializer(serializers.ModelSerializer):
    actor_email = serializers.SerializerMethodField()

    class Meta:
        model = AccessGrantEvent
        fields = ("id", "grant", "action", "actor", "actor_email", "note", "snapshot", "created_at")
        read_only_fields = fields

    def get_actor_email(self, obj):
        return getattr(obj.actor, "email", "") if obj.actor_id else ""


class ResourcePickerItemSerializer(serializers.Serializer):
    """One row in the resource picker (search results)."""

    resource_type = serializers.CharField()
    resource_id = serializers.IntegerField()
    label = serializers.CharField()
    subjects = serializers.ListField(child=serializers.CharField())
    published = serializers.BooleanField()
