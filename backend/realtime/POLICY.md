## Realtime event guarantees & sampling policy

This realtime layer is a **delivery hint bus**; clients always refetch canonical REST endpoints.

### Guarantees

- **High priority (`high`)**
  - **Never deduped** by the dedupe window (no `dedupe_key`).
  - **Never sampled/dropped** by backpressure controls.
  - **Delivered ahead of medium/low** on Redis (priority channels) and DB replay (priority ordering).
  - **Durable**: always written to `RealtimeEvent` outbox.

- **Medium priority (`medium`)**
  - Deduped within a time window when logically equivalent (same `dedupe_key`).
  - Under **critical** backpressure, may be dropped only if `REALTIME_BP_DROP_MEDIUM_AT_CRITICAL=True`.
  - Durable unless explicitly configured to drop at critical.

- **Low priority (`low`)**
  - Deduped with a **larger window** than default to reduce write amplification.
  - May be **sampled** before outbox insertion via `REALTIME_LOW_PRIORITY_DB_SAMPLE_RATE` and dynamic backpressure.
  - Under **critical** backpressure, may be **dropped** by producer throttling.
  - If a low event is sampled/dropped **before** DB write, it will **not** be replayed after reconnect.

### Which event types are safe to sample/drop

Allowed best-effort (typical):
- `comments.updated`
- minor `stream.updated` reasons that only refresh UI chrome

NOT safe to sample/drop (must remain `high`):
- grade/score updates (`reason=grade`, any `grade.*`)
- assignment creation (`reason=assignment_created`)

### Operational knobs

- `REALTIME_LOW_PRIORITY_DB_SAMPLE_RATE`: baseline low sampling rate (0..1).
- `REALTIME_LOW_PRIORITY_DEDUPE_SECONDS`: baseline low dedupe window.
- Backpressure thresholds: `REALTIME_BP_*` env vars.
- Critical drops:
  - `REALTIME_BP_DROP_LOW_AT_CRITICAL`
  - `REALTIME_BP_DROP_MEDIUM_AT_CRITICAL`

