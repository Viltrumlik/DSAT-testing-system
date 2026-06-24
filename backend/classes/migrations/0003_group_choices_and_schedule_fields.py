import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("classes", "0002_group_fields_and_homework_files"),
    ]

    operations = [
        # Remove old fields
        migrations.RemoveField(model_name="classroom", name="section"),
        migrations.RemoveField(model_name="classroom", name="description"),
        migrations.RemoveField(model_name="classroom", name="lesson_schedule"),
        # Update subject to choices + required
        migrations.AlterField(
            model_name="classroom",
            name="subject",
            field=models.CharField(
                choices=[("ENGLISH", "English"), ("MATH", "Math")],
                db_index=True,
                max_length=20,
                default="ENGLISH",
            ),
            preserve_default=False,
        ),
        # New schedule fields
        migrations.AddField(
            model_name="classroom",
            name="lesson_days",
            field=models.CharField(
                choices=[("ODD", "Odd days"), ("EVEN", "Even days")],
                db_index=True,
                max_length=10,
                default="ODD",
            ),
        ),
        migrations.AddField(
            model_name="classroom",
            name="lesson_time",
            field=models.CharField(blank=True, help_text="Example: 18:00", max_length=40),
        ),
        migrations.AddField(
            model_name="classroom",
            name="lesson_hours",
            field=models.PositiveIntegerField(default=2, help_text="Lesson duration in hours"),
        ),
        migrations.AddField(
            model_name="classroom",
            name="start_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="classroom",
            name="room_number",
            field=models.CharField(blank=True, max_length=30),
        ),
        migrations.AddField(
            model_name="classroom",
            name="telegram_chat_url",
            field=models.URLField(blank=True),
        ),
    ]

