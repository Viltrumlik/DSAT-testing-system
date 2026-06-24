from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("exams", "0015_portalmockexam"),
    ]

    operations = [
        migrations.AddField(
            model_name="mockexam",
            name="is_published",
            field=models.BooleanField(
                db_index=True,
                default=False,
                help_text="When True, students with portal access see this mock and section rows may appear in Practice Tests.",
            ),
        ),
        migrations.AddField(
            model_name="mockexam",
            name="published_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
