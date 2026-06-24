import Cookies from "js-cookie";

const STORAGE_KEY = "mastersat_auth_telemetry_queue_v1";
const MAX_QUEUED_EVENTS = 300;
/** Beyond this, flush ASAP to avoid backlog under abuse or flaky networks. */
const IMMEDIATE_FLUSH_THRESHOLD = 92;

/** Debounced immediate flush after high-signal telemetry (loss spikes, guard anomalies). */
let criticalTelemetryFlushPending: number | null = null;
const CRITICAL_TELEM_DEBOUNCE_MS = 320;

export function flushCriticalTelemetrySoon(): void {
  if (typeof window === "undefined") return;
  if (criticalTelemetryFlushPending != null) return;
  criticalTelemetryFlushPending = window.setTimeout(() => {
    criticalTelemetryFlushPending = null;
    void flushAuthTelemetryQueue();
  }, CRITICAL_TELEM_DEBOUNCE_MS);
}

export type AuthTelemetryQueueEvent =
  | { k: "loss"; reason: string; t: number }
  | { k: "refresh"; t: number }
  | { k: "cancel"; t: number }
  | { k: "guard_peak"; depth: number; t: number };

type QueueFile = { v: 1; events: AuthTelemetryQueueEvent[] };

export function getQueuedTelemetryLength(): number {
  return loadQueue().events.length;
}

function loadQueue(): QueueFile {
  if (typeof window === "undefined") return { v: 1, events: [] };
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { v: 1, events: [] };
    const parsed = JSON.parse(raw) as Partial<QueueFile>;
    if (parsed?.v !== 1 || !Array.isArray(parsed.events)) return { v: 1, events: [] };
    return { v: 1, events: parsed.events.filter((e) => e && typeof e === "object") as AuthTelemetryQueueEvent[] };
  } catch {
    return { v: 1, events: [] };
  }
}

function saveQueue(q: QueueFile): void {
  if (typeof window === "undefined") return;
  try {
    while (q.events.length > MAX_QUEUED_EVENTS) {
      q.events.shift();
    }
    localStorage.setItem(STORAGE_KEY, JSON.stringify(q));
  } catch {
    /* quota / private mode */
  }
}

/** Persisted client-side so auth-related counters survive hard refresh before flush. */
export function enqueueAuthTelemetryEvent(ev: AuthTelemetryQueueEvent): void {
  if (typeof window === "undefined") return;
  try {
    const q = loadQueue();
    q.events.push(ev);
    while (q.events.length > MAX_QUEUED_EVENTS) {
      q.events.shift();
    }
    saveQueue(q);
    if (q.events.length >= IMMEDIATE_FLUSH_THRESHOLD) {
      queueMicrotask(() => void flushAuthTelemetryQueue());
    }
    if (ev.k === "loss" || ev.k === "guard_peak") {
      flushCriticalTelemetrySoon();
    }
  } catch {
    /* ignore */
  }
}

function clearQueuedEvents(): void {
  saveQueue({ v: 1, events: [] });
}

const LOSS_REASONS = new Set(["EXPIRED", "NETWORK", "SERVER", "NO_SESSION"]);

function correlHeadersFromConcurrency(ac: typeof import("./authConcurrency")): Record<string, string> {
  const IS_PROD = process.env.NODE_ENV === "production";
  const verbose = process.env.NEXT_PUBLIC_MASTERSAT_AUTH_CORREL_HEADERS === "1";
  const rawBoot = ac.getClientAuthBootState();
  const boot =
    rawBoot === "UNKNOWN"
      ? "BOOTING"
      : rawBoot === "BOOTING" || rawBoot === "AUTHENTICATED" || rawBoot === "UNAUTHENTICATED"
        ? rawBoot
        : "BOOTING";
  const h: Record<string, string> = {
    "X-Mastersat-Auth-Boot": boot,
    "X-Mastersat-Auth-Loss-Active": ac.getAuthLossActive() ? "1" : "0",
    "X-Mastersat-Me-Guard-Depth": String(Math.min(8, Math.max(0, ac.getMeInteractionGuardDepth()))),
  };
  if (!IS_PROD || verbose) {
    h["X-Mastersat-Auth-Loss-Ver"] = String(ac.getAuthLossVersion());
    h["X-Mastersat-Auth-Recovery-Ver"] = String(ac.getAuthRecoveryVersion());
    const r = ac.getLastAuthLossReason();
    if (r && LOSS_REASONS.has(r)) {
      h["X-Mastersat-Auth-Loss-Reason"] = r;
    }
    const la = ac.getLastAuthLossAt();
    if (la != null) h["X-Mastersat-Auth-Loss-At"] = String(la);
    const ra = ac.getLastAuthRecoveryAt();
    if (ra != null) h["X-Mastersat-Auth-Recovery-At"] = String(ra);
  }
  return h;
}

function buildCorrelBody(ac: typeof import("./authConcurrency")) {
  return {
    auth_boot: ac.getClientAuthBootState(),
    auth_loss_version: ac.getAuthLossVersion(),
    auth_recovery_version: ac.getAuthRecoveryVersion(),
    auth_loss_reason: ac.getLastAuthLossReason(),
    me_guard_depth: ac.getMeInteractionGuardDepth(),
    last_auth_loss_at: ac.getLastAuthLossAt(),
    last_auth_recovery_at: ac.getLastAuthRecoveryAt(),
    me_guard_depth_max: ac.getMeInteractionGuardDepthMax(),
  };
}

async function buildPayload(): Promise<object | null> {
  const ac = await import("./authConcurrency");
  const q = loadQueue();
  const events = [...q.events];
  if (events.length === 0) return null;
  return {
    schema: 1 as const,
    client_ts: Date.now(),
    events,
    snapshot: ac.getAuthTelemetrySnapshot(),
    correl: buildCorrelBody(ac),
  };
}

export async function flushAuthTelemetryQueue(): Promise<void> {
  if (typeof window === "undefined") return;
  try {
    const ac = await import("./authConcurrency");
    const payload = await buildPayload();
    if (!payload) return;

    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      ...correlHeadersFromConcurrency(ac),
    };
    const csrf = Cookies.get("csrftoken");
    if (csrf) headers["X-CSRFToken"] = csrf;

    const res = await fetch("/api/auth/client-telemetry/", {
      method: "POST",
      credentials: "same-origin",
      headers,
      body: JSON.stringify(payload),
    });
    if (res.ok) {
      clearQueuedEvents();
    }
  } catch {
    /* next adaptive tick retries */
  }
}

/**
 * Browser unload hook: beacon has no delivery guarantee — queue is intentionally left
 * in localStorage unless a successful flushed request cleared it earlier.
 */
export function flushAuthTelemetryBeacon(): void {
  if (typeof window === "undefined") return;
  try {
    const q = loadQueue();
    if (q.events.length === 0) return;
    void import("./authConcurrency").then((ac) => {
      const queued = [...q.events];
      if (queued.length === 0) return;
      const payload = JSON.stringify({
        schema: 1 as const,
        client_ts: Date.now(),
        events: queued,
        snapshot: ac.getAuthTelemetrySnapshot(),
        correl: buildCorrelBody(ac),
      });
      const blob = new Blob([payload], { type: "application/json" });
      navigator.sendBeacon("/api/auth/client-telemetry/", blob);
    });
  } catch {
    /* ignore */
  }
}

let flushTimerId: number | null = null;
let flushLoopActive = false;

function nextFlushDelayMs(queueLen: number): number {
  if (queueLen >= 220) return 3_500;
  if (queueLen >= 140) return 7_000;
  if (queueLen >= 72) return 12_000;
  return 28_000;
}

async function adaptiveFlushTick(): Promise<void> {
  if (!flushLoopActive) return;
  const backlog = loadQueue().events.length;
  await flushAuthTelemetryQueue();
  if (!flushLoopActive) return;
  const remained = loadQueue().events.length;
  const scheduleFrom = Math.max(backlog, remained);
  const ms = nextFlushDelayMs(scheduleFrom);
  flushTimerId = window.setTimeout(() => void adaptiveFlushTick(), ms);
}

export function startAuthTelemetryFlushLoop(): void {
  if (typeof window === "undefined") return;
  if (flushLoopActive) return;
  flushLoopActive = true;
  window.addEventListener("beforeunload", flushAuthTelemetryBeacon);
  flushTimerId = window.setTimeout(() => void adaptiveFlushTick(), 900);
}

export function stopAuthTelemetryFlushLoop(): void {
  flushLoopActive = false;
  window.removeEventListener("beforeunload", flushAuthTelemetryBeacon);
  if (flushTimerId !== null) {
    window.clearTimeout(flushTimerId);
    flushTimerId = null;
  }
}
