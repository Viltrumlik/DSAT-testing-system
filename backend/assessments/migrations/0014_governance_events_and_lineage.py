"""
Migration 0014 — Governance events table + AssessmentSetVersion lineage chain.

CHANGES:
  1. governance_events table (GovernanceEvent model)
       - Immutable, append-only audit event store for all governance actions.
       - Polymorphic entity reference (entity_type + entity_id).
       - actor_email denormalized for audit stability.
       - Three composite indexes for operator query patterns.

  2. assessment_set_versions.previous_version_id (nullable FK → self)
       - Lineage chain: each version points to its predecessor.
       - NULL for the first version of a set.
       - PROTECT on_delete — predecessor versions cannot be deleted.
       - Enables supersession graph traversal and diff queries.

ROLLBACK SAFETY:
  - Both changes are purely additive. No existing tables or columns are
    modified. Roll back by dropping the new table and column.
  - previous_version_id is nullable — existing versions get NULL (correct:
    they were created before lineage tracking, their predecessor is unknown).
    A backfill can set previous_version_id based on version_number ordering
    after this migration runs.
"""

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("assessments", "0013_nullable_set_version_fk"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ── 1. previous_version FK on AssessmentSetVersion ──────────────────
        migrations.AddField(
            model_name="assessmentsetversion",
            name="previous_version",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="successor_versions",
                to="assessments.assessmentsetversion",
                help_text="The immediately preceding published version (null = first version).",
            ),
        ),

        # ── 2. governance_events table ───────────────────────────────────────
        migrations.CreateModel(
            name="GovernanceEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event_type", models.CharField(
                    choices=[
                        ("publish", "Published"),
                        ("publish_idempotent", "Publish (idempotent — identical content)"),
                        ("publish_validation_failed", "Publish validation failed"),
                        ("supersede", "Superseded by new version"),
                        ("assignment_pin", "Assignment version pinned"),
                        ("attempt_snapshot_pin", "Attempt snapshot pinned"),
                        ("scoring_start", "Scoring started"),
                        ("scoring_complete", "Scoring completed"),
                        ("scoring_retry", "Scoring retried"),
                        ("scoring_failure", "Scoring failed"),
                        ("scoring_override", "Scoring overridden"),
                        ("integrity_failure", "Integrity failure detected"),
                        ("integrity_repair", "Integrity repair performed"),
                        ("fallback_path_used", "Live-read fallback path used (pre-snapshot attempt)"),
                    ],
                    db_index=True,
                    max_length=64,
                )),
                ("entity_type", models.CharField(db_index=True, max_length=64)),
                ("entity_id", models.BigIntegerField(db_index=True)),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="governance_events",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                ("actor_email", models.CharField(blank=True, db_index=True, default="", max_length=254)),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("correlation_id", models.CharField(blank=True, db_index=True, default="", max_length=128)),
                ("occurred_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
            ],
            options={
                "db_table": "governance_events",
                "ordering": ["-occurred_at", "-id"],
            },
        ),
        migrations.AddIndex(
            model_name="governanceevent",
            index=models.Index(
                fields=["entity_type", "entity_id", "occurred_at"],
                name="gov_ev_entity_timeline_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="governanceevent",
            index=models.Index(
                fields=["event_type", "occurred_at"],
                name="gov_ev_type_timeline_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="governanceevent",
            index=models.Index(
                fields=["actor_email", "occurred_at"],
                name="gov_ev_actor_timeline_idx",
            ),
        ),
    ]
