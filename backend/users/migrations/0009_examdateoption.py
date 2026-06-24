# SAT exam date options (admin-managed list).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0008_user_telegram_id"),
    ]

    operations = [
        migrations.CreateModel(
            name="ExamDateOption",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("exam_date", models.DateField(db_index=True, unique=True)),
                ("label", models.CharField(blank=True, default="", max_length=200)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "db_table": "users_exam_date_option",
                "ordering": ["sort_order", "exam_date"],
            },
        ),
    ]
