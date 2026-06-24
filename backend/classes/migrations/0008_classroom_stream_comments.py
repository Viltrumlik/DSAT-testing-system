import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("classes", "0007_assignment_practice_scope"),
    ]

    operations = [
        migrations.CreateModel(
            name="ClassroomStreamItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "stream_type",
                    models.CharField(
                        choices=[("post", "Post"), ("assignment", "Assignment"), ("submission", "Submission")],
                        db_index=True,
                        max_length=20,
                    ),
                ),
                ("related_id", models.PositiveIntegerField()),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "actor",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="classroom_stream_actions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "classroom",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="stream_items",
                        to="classes.classroom",
                    ),
                ),
            ],
            options={
                "db_table": "classroom_stream_items",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="classroomstreamitem",
            constraint=models.UniqueConstraint(fields=("stream_type", "related_id"), name="classroom_stream_unique_type_related"),
        ),
        migrations.AddIndex(
            model_name="classroomstreamitem",
            index=models.Index(fields=["classroom", "created_at"], name="cls_stream_clsroom_created"),
        ),
        migrations.CreateModel(
            name="ClassComment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "target_type",
                    models.CharField(
                        choices=[("post", "Post"), ("assignment", "Assignment")],
                        db_index=True,
                        max_length=20,
                    ),
                ),
                ("target_id", models.PositiveIntegerField()),
                ("content", models.TextField(max_length=10000)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "author",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="class_comments",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "classroom",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="comments",
                        to="classes.classroom",
                    ),
                ),
                (
                    "parent",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="replies",
                        to="classes.classcomment",
                    ),
                ),
            ],
            options={
                "db_table": "class_comments",
                "ordering": ["created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="classcomment",
            index=models.Index(fields=["classroom", "target_type", "target_id"], name="cls_comment_target_idx"),
        ),
    ]
