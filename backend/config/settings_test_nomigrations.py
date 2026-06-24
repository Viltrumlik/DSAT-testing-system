"""
Test settings that build the test DB straight from the current models, skipping
the migration history entirely.

Why: under Django 6.x the local environment trips a latent historical-migration
conflict in `exams` (a duplicate option_a_image add) when constructing a fresh
test database. CI runs a pinned (5.x) Django and is unaffected. For local
verification we bypass migrations so tables are created from model state — this
exercises the real schema without replaying the broken history.

Usage:
    python manage.py test questionbank --settings=config.settings_test_nomigrations
"""
from .settings import *  # noqa: F401,F403


class _DisableMigrations:
    def __contains__(self, item):
        return True

    def __getitem__(self, item):
        return None


MIGRATION_MODULES = _DisableMigrations()
