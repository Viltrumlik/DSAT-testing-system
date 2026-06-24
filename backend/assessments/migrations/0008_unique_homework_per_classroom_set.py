from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("assessments", "0007_alter_assessmentset_category_length"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="homeworkassignment",
            constraint=models.UniqueConstraint(
                fields=["classroom", "assessment_set"],
                name="uniq_assessment_hw_classroom_set",
            ),
        ),
    ]

