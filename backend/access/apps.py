from django.apps import AppConfig


class AccessConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "access"
    verbose_name = "Access control (RBAC/ABAC)"

    def ready(self):
        # Wire core event handlers (best-effort import).
        try:
            from core.events import get_event_bus
            from core.events.events import SessionRevoked
            from core.metrics import incr

            bus = get_event_bus()

            def _on_session_revoked(evt: SessionRevoked) -> None:
                incr("auth.session_revoked")

            bus.subscribe(SessionRevoked, _on_session_revoked)
        except Exception:
            pass

        # Access engine dual-write signal mirroring. Handlers are inert unless
        # ACCESS_ENGINE_DUAL_WRITE is enabled; connecting them is always safe.
        try:
            from access.engine import dual_write

            dual_write.connect()
        except Exception:  # pragma: no cover - never block app startup
            import logging

            logging.getLogger("access.dual_write").exception(
                "failed to connect access dual-write signals"
            )
