import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("exams", "0024_mockexam_midterm_target_question_count"),
    ]

    operations = [
        migrations.CreateModel(
            name="BulkAssignmentDispatch",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("pastpaper", "Pastpaper library"),
                            ("timed_mock", "Timed mock"),
                            ("mixed", "Mixed"),
                        ],
                        db_index=True,
                        max_length=20,
                    ),
                ),
                ("subject_summary", models.CharField(blank=True, default="", max_length=200)),
                ("students_requested_count", models.PositiveIntegerField(default=0)),
                ("students_granted_count", models.PositiveIntegerField(default=0)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("delivered", "Delivered"),
                            ("completed", "Completed"),
                            ("failed", "Failed"),
                        ],
                        db_index=True,
                        default="delivered",
                        max_length=20,
                    ),
                ),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("result", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "assigned_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="bulk_library_dispatches",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "rerun_of",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="reruns",
                        to="exams.bulkassignmentdispatch",
                    ),
                ),
            ],
            options={
                "db_table": "exams_bulk_assignment_dispatch",
                "ordering": ["-created_at"],
            },
        ),
    ]
