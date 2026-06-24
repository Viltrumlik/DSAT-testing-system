from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):

    dependencies = [
        ("classes", "0014_submission_revision_stale_blob_tracking"),
    ]

    operations = [
        migrations.AddField(
            model_name="submissionfile",
            name="content_sha256",
            field=models.CharField(blank=True, db_index=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="submissionfile",
            name="upload_token",
            field=models.CharField(blank=True, db_index=True, default="", max_length=64),
        ),
        migrations.AddConstraint(
            model_name="submissionfile",
            constraint=models.UniqueConstraint(
                fields=("submission", "upload_token"),
                name="uniq_submission_file_upload_token_nonempty",
                condition=Q(upload_token__gt=""),
            ),
        ),
        migrations.AddConstraint(
            model_name="submissionfile",
            constraint=models.UniqueConstraint(
                fields=("submission", "content_sha256"),
                name="uniq_submission_file_sha_nonempty",
                condition=Q(content_sha256__gt=""),
            ),
        ),
    ]
