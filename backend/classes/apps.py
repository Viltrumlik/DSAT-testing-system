from django.apps import AppConfig


def _default_cache_is_redis() -> bool:
    from django.conf import settings

    backend = str(settings.CACHES.get("default", {}).get("BACKEND", "")).lower()
    return "redis" in backend


class ClassesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "classes"

    def ready(self) -> None:
        # Stream feed + comment cleanup signals (derived layer; core models unchanged).
        import classes.stream_signals  # noqa: F401
        import classes.homework_attempt_signals  # noqa: F401

        from django.conf import settings
        from django.core.exceptions import ImproperlyConfigured

        if getattr(settings, "CLASSROOM_ENFORCE_REDIS_CACHE", False) and not _default_cache_is_redis():
            raise ImproperlyConfigured(
                "CLASSROOM_ENFORCE_REDIS_CACHE is enabled but CACHES['default'] is not Redis. "
                "Set REDIS_URL so throttling and shared homework state work across workers."
            )
        if getattr(settings, "CLASSROOM_METRICS_REQUIRE_SHARED_CACHE", False) and not _default_cache_is_redis():
            raise ImproperlyConfigured(
                "CLASSROOM_METRICS_REQUIRE_SHARED_CACHE is enabled but CACHES['default'] is not Redis. "
                "Use REDIS_URL for accurate homework submit metrics, or disable the flag for local dev."
            )

