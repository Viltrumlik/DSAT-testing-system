from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0003_user_is_frozen"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="profile_image",
            field=models.ImageField(blank=True, null=True, upload_to="profiles/"),
        ),
        migrations.AddField(
            model_name="user",
            name="sat_exam_date",
            field=models.DateField(blank=True, help_text="Planned SAT exam date", null=True),
        ),
        migrations.AddField(
            model_name="user",
            name="target_score",
            field=models.PositiveIntegerField(
                blank=True, help_text="Target total SAT score (400–1600)", null=True
            ),
        ),
    ]
