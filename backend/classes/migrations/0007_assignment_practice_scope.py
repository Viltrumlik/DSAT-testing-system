from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("classes", "0006_assignment_extra_attachments"),
    ]

    operations = [
        migrations.AddField(
            model_name="assignment",
            name="practice_scope",
            field=models.CharField(
                choices=[
                    ("BOTH", "Both (English & Math)"),
                    ("ENGLISH", "English (Reading & Writing) only"),
                    ("MATH", "Math only"),
                ],
                default="BOTH",
                help_text="For mock or pastpaper with multiple sections: assign all, English only, or Math only.",
                max_length=20,
            ),
        ),
    ]
