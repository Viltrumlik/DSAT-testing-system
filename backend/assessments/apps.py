import sys

from django.apps import AppConfig


def _default_cache_is_redis() -> bool:
    from django.conf import settings

    backend = str(settings.CACHES.get("default", {}).get("BACKEND", "")).lower()
    return "redis" in backend


def _running_tests() -> bool:
    return any(a in ("test", "pytest") for a in sys.argv)


class AssessmentsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "assessments"

    def ready(self) -> None:
        from django.conf import settings
        from django.core.exceptions import ImproperlyConfigured

        if _running_tests():
            return

        if getattr(settings, "ASSESSMENT_ENFORCE_REDIS_CACHE", False) and not _default_cache_is_redis():
            raise ImproperlyConfigured(
                "ASSESSMENT_ENFORCE_REDIS_CACHE is enabled but CACHES['default'] is not Redis. "
                "Set REDIS_URL so assignment throttles and abuse counters work across workers."
            )
