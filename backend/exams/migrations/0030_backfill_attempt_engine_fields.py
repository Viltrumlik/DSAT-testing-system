from django.db import migrations


def backfill_engine_fields(apps, schema_editor):
    TestAttempt = apps.get_model("exams", "TestAttempt")
    Module = apps.get_model("exams", "Module")

    # best-effort: infer state + timestamps from legacy fields.
    for att in TestAttempt.objects.all().only(
        "id",
        "is_completed",
        "started_at",
        "submitted_at",
        "current_module_id",
        "current_module_start_time",
        "module_answers",
        "version_number",
        "current_state",
        "completed_at",
    ).iterator(chunk_size=500):
        updates = {}

        # State
        if att.is_completed:
            updates["current_state"] = "COMPLETED"
        else:
            # Determine current module order if any
            mod_order = None
            if att.current_module_id:
                m = Module.objects.filter(pk=att.current_module_id).first()
                mod_order = getattr(m, "module_order", None)
            if mod_order == 2:
                updates["current_state"] = "MODULE_2_ACTIVE"
            elif mod_order == 1:
                updates["current_state"] = "MODULE_1_ACTIVE"
            else:
                # fall back based on which module ids exist in answers
                answered_ids = []
                try:
                    answered_ids = [int(x) for x in (att.module_answers or {}).keys()]
                except Exception:
                    answered_ids = []
                if answered_ids:
                    orders = list(
                        Module.objects.filter(id__in=answered_ids).values_list("module_order", flat=True)
                    )
                    if 2 in orders:
                        updates["current_state"] = "MODULE_2_SUBMITTED"
                    elif 1 in orders:
                        updates["current_state"] = "MODULE_1_SUBMITTED"
                    else:
                        updates["current_state"] = "NOT_STARTED"
                else:
                    updates["current_state"] = "NOT_STARTED"

        # Timestamps
        if att.started_at and not getattr(att, "module_1_started_at", None):
            updates["module_1_started_at"] = att.started_at
        if att.submitted_at and not getattr(att, "completed_at", None):
            updates["completed_at"] = att.submitted_at

        # Legacy current_module_start_time maps to whichever module is active.
        if att.current_module_id and att.current_module_start_time:
            m = Module.objects.filter(pk=att.current_module_id).first()
            if m and m.module_order == 1 and not getattr(att, "module_1_started_at", None):
                updates["module_1_started_at"] = att.current_module_start_time
            if m and m.module_order == 2 and not getattr(att, "module_2_started_at", None):
                updates["module_2_started_at"] = att.current_module_start_time

        if updates:
            TestAttempt.objects.filter(pk=att.pk).update(**updates)


class Migration(migrations.Migration):

    dependencies = [
        ("exams", "0029_attempt_engine_fields_v2"),
    ]

    operations = [
        migrations.RunPython(backfill_engine_fields, migrations.RunPython.noop),
    ]

