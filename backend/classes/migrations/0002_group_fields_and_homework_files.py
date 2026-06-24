from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("classes", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="classroom",
            name="subject",
            field=models.CharField(blank=True, db_index=True, max_length=80),
        ),
        migrations.AddField(
            model_name="classroom",
            name="lesson_schedule",
            field=models.CharField(
                blank=True,
                help_text="Lesson days and time, e.g. Mon/Wed/Fri 18:00",
                max_length=120,
            ),
        ),
        migrations.AddField(
            model_name="classroom",
            name="max_students",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="assignment",
            name="attachment_file",
            field=models.FileField(blank=True, null=True, upload_to="homework_files/"),
        ),
        migrations.RenameField(
            model_name="submission",
            old_name="student_comment",
            new_name="text_response",
        ),
        migrations.AddField(
            model_name="submission",
            name="upload_file",
            field=models.FileField(blank=True, null=True, upload_to="homework_submissions/"),
        ),
    ]

