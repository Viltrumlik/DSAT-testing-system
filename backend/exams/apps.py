from django.apps import AppConfig


class ExamsConfig(AppConfig):
    name = "exams"

    def ready(self):
        # Register signal receivers (question ordering invariants).
        from . import signal_handlers  # noqa: F401
