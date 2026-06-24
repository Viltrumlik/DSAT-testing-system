"""UAT settings — a clean, runnable Classroom acceptance environment.

Builds the schema directly from current model state (migrations disabled, same mechanism as
settings_test_nomigrations) into a dedicated `uat.sqlite3`, side-stepping the pre-existing
historical-migration drift in `exams` that affects the local `db.sqlite3`. For local/staging
UAT only — never production.

Usage:
    python manage.py migrate --settings=config.settings_uat
    python manage.py seed_classroom_uat --settings=config.settings_uat
    python manage.py runserver --settings=config.settings_uat
"""

from .settings import *  # noqa: F401,F403
from .settings import BASE_DIR


class _DisableMigrations:
    def __contains__(self, item):
        return True

    def __getitem__(self, item):
        return None


MIGRATION_MODULES = _DisableMigrations()

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "uat.sqlite3",
    }
}

DEBUG = True
