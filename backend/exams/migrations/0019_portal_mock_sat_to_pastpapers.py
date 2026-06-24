from django.db import migrations, models


def portal_mock_sat_to_pastpapers(apps, schema_editor):
    """
    Student Mock Exam page entries (PortalMockExam + MOCK_SAT) become standalone
    pastpaper PracticeTests; portal row and MockExam shell are removed.
    Midterm mocks are unchanged.
    """
    PortalMockExam = apps.get_model("exams", "PortalMockExam")
    PracticeTest = apps.get_model("exams", "PracticeTest")
    MockExam = apps.get_model("exams", "MockExam")

    for portal in PortalMockExam.objects.select_related("mock_exam").all():
        mock = portal.mock_exam
        if mock.kind == "MIDTERM":
            continue

        pts = list(PracticeTest.objects.filter(mock_exam_id=mock.id))
        portal_ids = list(portal.assigned_users.values_list("id", flat=True))
        mock_ids = list(mock.assigned_users.values_list("id", flat=True))
        uid_set = set(portal_ids) | set(mock_ids)

        if not pts:
            mock.delete()
            continue

        n = len(pts)
        for pt in pts:
            title_empty = not (getattr(pt, "title", None) or "").strip()
            if title_empty:
                if n == 1:
                    pt.title = mock.title
                else:
                    subj = "Math" if pt.subject == "MATH" else "Reading & Writing"
                    pt.title = f"{mock.title} — {subj}"
            pt.mock_exam_id = None
            pt.practice_date = mock.practice_date
            pt.save()

            existing = set(pt.assigned_users.values_list("id", flat=True))
            for uid in uid_set:
                if uid not in existing:
                    pt.assigned_users.add(uid)

        mock.delete()


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("exams", "0018_practicetest_title"),
    ]

    operations = [
        migrations.AddField(
            model_name="practicetest",
            name="practice_date",
            field=models.DateField(
                blank=True,
                db_index=True,
                help_text="Optional official/exam date shown on student practice cards.",
                null=True,
            ),
        ),
        migrations.RunPython(portal_mock_sat_to_pastpapers, noop_reverse),
    ]
