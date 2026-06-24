from django.db import migrations


def _infer_status(apps, attempt):
    Module = apps.get_model("exams", "Module")

    if getattr(attempt, "is_completed", False):
        return "COMPLETED"

    current_module_id = getattr(attempt, "current_module_id", None)
    if current_module_id:
        try:
            mod = Module.objects.get(pk=current_module_id)
            if mod.module_order == 2:
                return "MODULE_2_ACTIVE"
            if mod.module_order == 1:
                return "MODULE_1_ACTIVE"
        except Module.DoesNotExist:
            pass

    # completed_modules is M2M; infer from any completed module order.
    completed_ids = list(attempt.completed_modules.values_list("id", flat=True))
    if completed_ids:
        mods = list(Module.objects.filter(id__in=completed_ids).values_list("module_order", flat=True))
        if 2 in mods:
            # If module 2 is marked completed but is_completed is false, treat as completed (data repair).
            return "COMPLETED"
        if 1 in mods:
            return "MODULE_1_SUBMITTED"

    return "NOT_STARTED"


def backfill_status(apps, schema_editor):
    TestAttempt = apps.get_model("exams", "TestAttempt")

    qs = TestAttempt.objects.all().only("id", "is_completed", "current_module_id", "status")
    for att in qs.iterator(chunk_size=500):
        inferred = _infer_status(apps, att)
        updates = {}
        if getattr(att, "status", None) != inferred:
            updates["status"] = inferred
        if inferred == "COMPLETED" and not getattr(att, "is_completed", False):
            updates["is_completed"] = True
        if updates:
            TestAttempt.objects.filter(pk=att.pk).update(**updates)


class Migration(migrations.Migration):

    dependencies = [
        ("exams", "0027_testattempt_status_state_machine"),
    ]

    operations = [
        migrations.RunPython(backfill_status, migrations.RunPython.noop),
    ]

