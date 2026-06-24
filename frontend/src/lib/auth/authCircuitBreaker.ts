const WINDOW_MS = 130_000;
const TRIP_AFTER_TEMPORAL = 6;
/** Ignore new trips briefly after firing so refresh/re-auth cannot thrash open/trip/open. */
const TRIP_COOLDOWN_MS = 90_000;

const MAX_SAMPLES = 32;

let circuitCooldownUntil = 0;

function prune(ts: number[], now: number): void {
  const cutoff = now - WINDOW_MS;
  while (ts.length > 0) {
    const head = ts[0];
    if (head === undefined || head >= cutoff) break;
    ts.shift();
  }
}

function pushBounded(ts: number[], now: number): void {
  prune(ts, now);
  ts.push(now);
  while (ts.length > MAX_SAMPLES) ts.shift();
}

const temporalStaleAt: number[] = [];

export function resetAuthCircuitBreakerForTests(): void {
  temporalStaleAt.length = 0;
  circuitCooldownUntil = 0;
}

/** Successful `/users/me` — decay stress so one bad hour does not lock the account view. */
export function clearAuthCircuitWindow(): void {
  temporalStaleAt.length = 0;
  circuitCooldownUntil = 0;
}

/** True while ignoring fresh temporal samples (post-trip cooldown). Exposed for tests / diagnostics only. */
export function isAuthCircuitCooldownActive(nowMs: number = Date.now()): boolean {
  return nowMs < circuitCooldownUntil;
}

export function noteTemporalStaleRejection(): void {
  const now = Date.now();
  if (now < circuitCooldownUntil) return;
  pushBounded(temporalStaleAt, now);
}

/** @returns whether the circuit breaker just tripped */
export function evaluateAuthCircuitBreaker(): boolean {
  const now = Date.now();
  if (now < circuitCooldownUntil) return false;
  prune(temporalStaleAt, now);
  if (temporalStaleAt.length >= TRIP_AFTER_TEMPORAL) {
    temporalStaleAt.length = 0;
    circuitCooldownUntil = now + TRIP_COOLDOWN_MS;
    return true;
  }
  return false;
}
