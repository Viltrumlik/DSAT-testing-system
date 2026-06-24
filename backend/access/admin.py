from django.contrib import admin, messages
from django.utils import timezone

from .engine.access_service import AccessService
from .models import (
    AccessGrantEvent,
    Permission,
    ResourceAccessGrant,
    Role,
    RolePermission,
    UserAccess,
    UserPermission,
)


@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    list_display = ("codename", "name")
    search_fields = ("codename", "name")


class RolePermissionInline(admin.TabularInline):
    model = RolePermission
    extra = 0
    autocomplete_fields = ("permission",)


class RoleModelAdmin(admin.ModelAdmin):
    list_display = ("code", "name")
    search_fields = ("code", "name")
    inlines = [RolePermissionInline]


admin.site.register(Role, RoleModelAdmin)


@admin.register(UserPermission)
class UserPermissionAdmin(admin.ModelAdmin):
    list_display = ("user", "permission", "granted")
    list_filter = ("granted",)
    autocomplete_fields = ("user", "permission")


@admin.register(UserAccess)
class UserAccessAdmin(admin.ModelAdmin):
    list_display = ("user", "subject", "classroom", "granted_by", "created_at")
    list_filter = ("subject",)
    autocomplete_fields = ("user", "classroom", "granted_by")


# --- Access engine (Phase 2) ------------------------------------------------


class AccessGrantEventInline(admin.TabularInline):
    model = AccessGrantEvent
    extra = 0
    can_delete = False
    readonly_fields = ("action", "actor", "note", "snapshot", "created_at")
    ordering = ("-created_at",)

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(ResourceAccessGrant)
class ResourceAccessGrantAdmin(admin.ModelAdmin):
    list_display = (
        "id", "user", "scope", "subject", "resource_type", "resource_id",
        "classroom", "source", "status", "expires_at", "created_at",
    )
    list_filter = ("scope", "status", "source", "subject", "resource_type")
    search_fields = (
        "user__email", "user__username", "resource_type", "resource_id", "subject",
    )
    autocomplete_fields = ("user", "classroom", "granted_by")
    readonly_fields = ("created_at", "updated_at")
    date_hierarchy = "created_at"
    list_select_related = ("user", "classroom", "granted_by")
    inlines = [AccessGrantEventInline]
    actions = ("action_revoke", "action_extend_30_days", "action_restore")

    @admin.action(description="Revoke selected grants")
    def action_revoke(self, request, queryset):
        n = 0
        for g in queryset.filter(status=ResourceAccessGrant.STATUS_ACTIVE):
            AccessService.revoke(g, actor=request.user, note="admin action: revoke")
            n += 1
        self.message_user(request, f"Revoked {n} grant(s).", messages.SUCCESS)

    @admin.action(description="Extend selected grants by 30 days")
    def action_extend_30_days(self, request, queryset):
        new_expiry = timezone.now() + timezone.timedelta(days=30)
        n = 0
        for g in queryset:
            AccessService.extend(g, expires_at=new_expiry, actor=request.user,
                                 note="admin action: extend 30d")
            n += 1
        self.message_user(request, f"Extended {n} grant(s) to {new_expiry:%Y-%m-%d}.", messages.SUCCESS)

    @admin.action(description="Restore (re-activate) selected revoked/expired grants")
    def action_restore(self, request, queryset):
        n = 0
        for g in queryset.exclude(status=ResourceAccessGrant.STATUS_ACTIVE):
            g.status = ResourceAccessGrant.STATUS_ACTIVE
            g.save(update_fields=["status", "updated_at"])
            AccessGrantEvent.objects.create(
                grant=g, action=AccessGrantEvent.ACTION_RESTORED, actor=request.user,
                note="admin action: restore",
            )
            n += 1
        self.message_user(request, f"Restored {n} grant(s).", messages.SUCCESS)


@admin.register(AccessGrantEvent)
class AccessGrantEventAdmin(admin.ModelAdmin):
    """Read-only audit log."""

    list_display = ("id", "grant", "action", "actor", "created_at")
    list_filter = ("action",)
    search_fields = ("grant__id", "actor__email", "note")
    readonly_fields = ("grant", "action", "actor", "snapshot", "note", "created_at")
    date_hierarchy = "created_at"
    list_select_related = ("grant", "actor")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
