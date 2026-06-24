from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("assessments", "0016_assessmentquestion_question_image"),
    ]

    operations = [
        migrations.AddField(
            model_name="assessmentquestion",
            name="question_prompt",
            field=models.TextField(blank=True, default=""),
        ),
    ]
