from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("classes", "0017_alter_classroom_schedule_summary_default"),
    ]

    operations = [
        migrations.CreateModel(
            name="AssessmentSet",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "subject",
                    models.CharField(
                        choices=[("math", "Math"), ("english", "English")],
                        db_index=True,
                        max_length=16,
                    ),
                ),
                ("category", models.CharField(blank=True, db_index=True, default="", max_length=120)),
                ("title", models.CharField(db_index=True, max_length=200)),
                ("description", models.TextField(blank=True, default="")),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True, db_index=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="assessment_sets_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "assessment_sets",
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.AddIndex(
            model_name="assessmentset",
            index=models.Index(fields=["subject", "category", "is_active"], name="assessment__subject_7d4b5e_idx"),
        ),
        migrations.CreateModel(
            name="AssessmentQuestion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("order", models.PositiveIntegerField(db_index=True, default=0)),
                ("prompt", models.TextField()),
                (
                    "question_type",
                    models.CharField(
                        choices=[
                            ("multiple_choice", "Multiple choice"),
                            ("short_text", "Short text"),
                            ("numeric", "Numeric"),
                            ("boolean", "True/False"),
                        ],
                        db_index=True,
                        max_length=32,
                    ),
                ),
                ("choices", models.JSONField(blank=True, default=list)),
                ("correct_answer", models.JSONField(blank=True, default=None, null=True)),
                ("grading_config", models.JSONField(blank=True, default=dict)),
                ("points", models.PositiveIntegerField(default=1)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True, db_index=True)),
                (
                    "assessment_set",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="questions",
                        to="assessments.assessmentset",
                    ),
                ),
            ],
            options={
                "db_table": "assessment_questions",
                "ordering": ["assessment_set_id", "order", "id"],
            },
        ),
        migrations.AddIndex(
            model_name="assessmentquestion",
            index=models.Index(fields=["assessment_set", "order"], name="assessment__assessm_dcb17a_idx"),
        ),
        migrations.CreateModel(
            name="HomeworkAssignment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "assessment_set",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="homework_assignments",
                        to="assessments.assessmentset",
                    ),
                ),
                (
                    "assigned_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="assessment_homework_assigned",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "assignment",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="assessment_homework",
                        to="classes.assignment",
                    ),
                ),
                (
                    "classroom",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="assessment_homework",
                        to="classes.classroom",
                    ),
                ),
            ],
            options={
                "db_table": "assessment_homework_assignments",
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.AddConstraint(
            model_name="homeworkassignment",
            constraint=models.UniqueConstraint(
                fields=("classroom", "assignment"),
                name="uniq_assessment_hw_class_assignment",
            ),
        ),
        migrations.CreateModel(
            name="AssessmentAttempt",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "status",
                    models.CharField(
                        choices=[("in_progress", "In progress"), ("submitted", "Submitted")],
                        db_index=True,
                        default="in_progress",
                        max_length=24,
                    ),
                ),
                ("started_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("submitted_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("total_time_seconds", models.PositiveIntegerField(default=0)),
                (
                    "homework",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="attempts",
                        to="assessments.homeworkassignment",
                    ),
                ),
                (
                    "student",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="assessment_attempts",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "assessment_attempts",
                "ordering": ["-started_at", "-id"],
            },
        ),
        migrations.AddIndex(
            model_name="assessmentattempt",
            index=models.Index(fields=["student", "homework", "status"], name="assessment__student_1c0f09_idx"),
        ),
        migrations.AddConstraint(
            model_name="assessmentattempt",
            constraint=models.UniqueConstraint(
                fields=("homework", "student", "status"),
                name="uniq_active_attempt_per_hw_student_status",
            ),
        ),
        migrations.CreateModel(
            name="AssessmentAnswer",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("answer", models.JSONField(blank=True, default=None, null=True)),
                ("time_spent_seconds", models.PositiveIntegerField(default=0)),
                ("is_correct", models.BooleanField(blank=True, db_index=True, null=True)),
                ("points_awarded", models.DecimalField(blank=True, decimal_places=2, max_digits=7, null=True)),
                ("answered_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True, db_index=True)),
                (
                    "attempt",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="answers",
                        to="assessments.assessmentattempt",
                    ),
                ),
                (
                    "question",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="answers",
                        to="assessments.assessmentquestion",
                    ),
                ),
            ],
            options={"db_table": "assessment_answers"},
        ),
        migrations.AddConstraint(
            model_name="assessmentanswer",
            constraint=models.UniqueConstraint(fields=("attempt", "question"), name="uniq_answer_per_attempt_question"),
        ),
        migrations.AddIndex(
            model_name="assessmentanswer",
            index=models.Index(fields=["attempt", "question"], name="assessment__attempt_7a3de9_idx"),
        ),
        migrations.CreateModel(
            name="AssessmentResult",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("score_points", models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ("max_points", models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ("percent", models.DecimalField(decimal_places=2, default=0, max_digits=6)),
                ("correct_count", models.PositiveIntegerField(default=0)),
                ("total_questions", models.PositiveIntegerField(default=0)),
                ("graded_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                (
                    "attempt",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="result",
                        to="assessments.assessmentattempt",
                    ),
                ),
            ],
            options={
                "db_table": "assessment_results",
                "ordering": ["-graded_at", "-id"],
            },
        ),
    ]

