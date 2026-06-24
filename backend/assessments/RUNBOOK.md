# Assessments grading ops runbook

This runbook covers the **automatic grading pipeline** (attempt submission → async grading → result persistence), the **dispatcher/backpressure**, and **SLO alerting**.

## Key endpoints (admin)

- `GET /api/assessments/admin/grading/metrics/`
  - DB-derived queue/latency/failure metrics + trends + broker queue best-effort (Redis) + worker snapshot (Celery inspect best-effort).
- `GET /api/assessments/admin/grading/metrics/prometheus/`
  - Prometheus text exposition for gauges (queue + worker snapshot).
- `GET /api/assessments/admin/homework/metrics/prometheus/`
  - Prometheus text exposition for **homework integrity counters** (duplicate prevented + repairs applied).
- `GET /api/assessments/admin/attempts/<attempt_id>/`
- `POST /api/assessments/admin/attempts/<attempt_id>/requeue/`
  - Only for `grading_status=failed`, subject to cooldown + max-per-attempt.
- `POST /api/assessments/admin/attempts/<attempt_id>/force-grade/`
  - Requires body `{ "confirm": "FORCE" }`.

## SLO alerts (Celery beat)

Task: `assessments.tasks.alert_on_assessment_slo` (default every 5 minutes)

Violations (default window: 1h):
- latency p90
- failure rate
- old pending backlog count

Delivery:
- webhook with retries (`ASSESSMENT_OPS_WEBHOOK_URL`, fallback to `CLASSROOM_OPS_WEBHOOK_URL`)
- email fallback (`CLASSROOM_OPS_EMAIL_RECIPIENTS`)
- always logs a CRITICAL line

Deduping:
- uses cache with `CLASSROOM_ALERT_COOLDOWN_SECONDS`

## Common incidents

### 1) Queue growth / grading lag

Symptoms:
- `pending_age_seconds.p90` rising
- `assessments_grading_pending` rising
- alerts firing for `old_pending_count` or latency

Actions:
- verify workers are up (metrics: `workers.workers`, Prom gauge `assessments_workers_active`)
- verify dispatcher is running (`dispatch_pending_grading` beat schedule)
- check capacity knobs:
  - `ASSESSMENT_GRADING_MAX_INFLIGHT`
  - `ASSESSMENT_GRADING_DISPATCH_BATCH`
  - `ASSESSMENT_GRADING_MAX_ENQUEUE_PER_MINUTE`
- scale Celery workers (increase concurrency / replicas)
- if broker is Redis, check `broker.queue_len` for actual backlog

### 2) Elevated failure rate

Symptoms:
- alerts for failure rate
- `failed_total` rising

Actions:
- inspect representative attempt via admin attempt status endpoint
- requeue a small sample (cooldown/limits enforced)
- if failures persist, use `force-grade` only for diagnostics (requires confirmation)
- check worker logs for traceback; focus on deterministic grader errors vs transient DB/broker errors

### 3) Alerts not arriving

Actions:
- confirm webhook URL configured
- confirm email recipients configured
- check CRITICAL log entries for alerts (delivery failures are logged)
- ensure shared cache is configured in production (dedupe + budgets depend on it)

## Homework integrity commands

### Audit

```bash
python manage.py audit_homework_integrity --json
```

Checks:
- duplicate homework rows per `(classroom, assessment_set)`
- homework rows whose linked `classes.Assignment.classroom_id` disagrees with homework `classroom_id`

### Repair (de-dupe)

Dry run:

```bash
python manage.py repair_homework_integrity --dry-run --json
```

Apply:

```bash
python manage.py repair_homework_integrity --json
```

Repairs:
- selects canonical homework per `(classroom, assessment_set)` (prefers one with attempts)
- migrates attempts + audit events from duplicates into canonical
- deletes duplicate homework via deleting its linked `Assignment` (CASCADE)

## Configuration knobs

- `ASSESSMENT_GRADING_MAX_INFLIGHT`
- `ASSESSMENT_GRADING_DISPATCH_BATCH`
- `ASSESSMENT_GRADING_MAX_ENQUEUE_PER_MINUTE`
- `ASSESSMENT_ADMIN_REQUEUE_COOLDOWN_SECONDS`
- `ASSESSMENT_ADMIN_REQUEUE_MAX_PER_ATTEMPT`
- `ASSESSMENT_ALERT_P90_LATENCY_SECONDS`
- `ASSESSMENT_ALERT_FAILURE_RATE_PCT`
- `ASSESSMENT_ALERT_PENDING_OLDER_THAN_SECONDS`
- `ASSESSMENT_ALERT_PENDING_OLDER_THAN_COUNT`

