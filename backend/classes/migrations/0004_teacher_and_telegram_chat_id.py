import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("classes", "0003_group_choices_and_schedule_fields"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveField(
            model_name="classroom",
            name="telegram_chat_url",
        ),
        migrations.AddField(
            model_name="classroom",
            name="telegram_chat_id",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name="classroom",
            name="teacher",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="teaching_classes",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]

