from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("assessments", "0015_assessment_question_explanation"),
    ]

    # NOTE: this migration originally added only ``question_image`` (its name).
    # The four ``option_*_image`` AddFields were erroneously added here later, while
    # ``0018_assessmentquestion_option_images`` already adds the same columns — so a
    # fresh build hit "duplicate column name: option_a_image" at 0018. The option
    # images belong to 0018; restored this migration to question_image only.
    # Forward-compatible: already-migrated DBs (prod) re-run nothing; the final model
    # state is unchanged (option images still added by 0018).
    operations = [
        migrations.AddField(
            model_name="assessmentquestion",
            name="question_image",
            field=models.ImageField(blank=True, null=True, upload_to="assessment_questions/"),
        ),
    ]
