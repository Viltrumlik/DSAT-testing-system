from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm

from .models import ExamDateOption, User


@admin.register(ExamDateOption)
class ExamDateOptionAdmin(admin.ModelAdmin):
    list_display = ["exam_date", "label", "is_active", "sort_order", "created_at"]
    list_filter = ["is_active"]
    list_editable = ["is_active", "sort_order"]
    ordering = ["sort_order", "exam_date"]
    search_fields = ["label"]


class CustomUserCreationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ("email", "system_role", "is_staff", "is_superuser")


class CustomUserChangeForm(UserChangeForm):
    class Meta:
        model = User
        fields = (
            "email",
            "username",
            "first_name",
            "last_name",
            "phone_number",
            "telegram_id",
            "profile_image",
            "sat_exam_date",
            "target_score",
            "system_role",
            "is_staff",
            "is_superuser",
        )


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    add_form = CustomUserCreationForm
    form = CustomUserChangeForm
    model = User
    list_display = ["email", "phone_number", "telegram_id", "system_role", "is_staff", "is_active", "is_frozen"]
    ordering = ["email"]
    fieldsets = (
        (None, {"fields": ("email", "username", "password")}),
        (
            "Personal info",
            {"fields": ("first_name", "last_name", "phone_number", "telegram_id", "profile_image", "sat_exam_date", "target_score", "target_english", "target_math")},
        ),
        (
            "Permissions",
            {
                "fields": (
                    "system_role",
                    "is_active",
                    "is_frozen",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "system_role",
                    "password1",
                    "password2",
                    "is_frozen",
                    "is_staff",
                    "is_superuser",
                ),
            },
        ),
    )
    search_fields = ("email", "phone_number", "username", "first_name", "last_name")
    autocomplete_fields = ("system_role",)
