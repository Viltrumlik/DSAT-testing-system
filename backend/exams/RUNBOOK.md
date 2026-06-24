# Exams integrity ops runbook

This runbook covers integrity audits/repairs for the SAT exam engine:
- attempts (state machine, active attempt uniqueness)
- modules (missing/duplicate `module_order`)
- test library pack/section metadata drift

## Metrics & health

- Prometheus (exams counters): `GET /api/exams/metrics/prometheus/`
- Readiness (hybrid): `GET /api/health/ready/`
  - fails hard if migrations pending or critical constraints missing
  - warns (200 + warnings) if duplicate active attempts exist

## Commands

### 1) Audit: exam engine integrity

Command:

```bash
python manage.py audit_exam_integrity --json
```

What it checks (high-signal):
- missing required modules per `PracticeTest`
- duplicate `(practice_test_id, module_order)` groups
- modules with zero questions
- attempts with impossible state pointers
- **duplicate active attempts per `(student, practice_test)`**

How to use:
- run first in prod to get counts + sample IDs
- keep the JSON output for incident notes

### 2) Repair: exam engine integrity

Command (dry run):

```bash
python manage.py repair_exam_integrity --dry-run --json
```

Command (apply):

```bash
python manage.py repair_exam_integrity --json
```

Repairs performed:
- create missing required modules (idempotent)
- merge duplicate module rows into canonical module (moves questions + completed_modules links)
- normalize invalid module orders / timers (optional `--fix-timers`)
- heal impossible attempt pointers/state mismatches
- **resolve duplicate active attempts** by selecting a canonical attempt and marking extras as `ABANDONED`

Safety notes:
- always run `--dry-run` first
- follow by re-running `audit_exam_integrity` to verify closure

### 3) Audit: test library integrity (packs/sections)

Command:

```bash
python manage.py audit_test_library_integrity --json
```

What it checks:
- packs with 0 or 1 sections
- pack/section signature drift (pack vs its sections’ `practice_date/form_type/label`)
- standalone sections not in packs
- suspicious titles (common concatenation corruption patterns)

### 4) Repair: test library integrity (packs/sections)

Command (dry run):

```bash
python manage.py repair_test_library_integrity --dry-run --json
```

Command (apply):

```bash
python manage.py repair_test_library_integrity --json
```

What it does:
- normalizes sections under a `PastpaperPack` to match the pack signature
  - `practice_date`, `form_type`, `label`

## Incident patterns

### “No TestAttempt matches query” (student sees 404)

Meaning:
- attempt id is stale/invalid or wrong-owner

Actions:
- check `audit_exam_integrity` for duplicate active attempts (can cause stale IDs)
- verify DB constraint `uniq_active_attempt_per_student_test` exists
- if duplicates exist: `repair_exam_integrity` then re-run audit

