from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("classes", "0016_homework_staged_upload"),
    ]

    operations = [
        migrations.AlterField(
            model_name="classroom",
            name="schedule_summary",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Optional day list for ODD groups on the class page. EVEN groups show EVEN; Monday/Saturday appear in the header.",
                max_length=240,
            ),
        ),
    ]
