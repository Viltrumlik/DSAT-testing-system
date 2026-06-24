# Generated manually: student-facing mock list uses portal_mock_exams only.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("exams", "0014_mockexam_assigned_users"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PortalMockExam",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                (
                    "assigned_users",
                    models.ManyToManyField(
                        blank=True,
                        help_text="Who sees this mock on the student Mock Exam page.",
                        related_name="assigned_portal_mock_exams",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "mock_exam",
                    models.OneToOneField(
                        help_text="Underlying mock (R&W/Math sections are PracticeTest rows; not exposed on the mock list API).",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="portal_listing",
                        to="exams.mockexam",
                    ),
                ),
            ],
            options={
                "db_table": "portal_mock_exams",
            },
        ),
    ]
