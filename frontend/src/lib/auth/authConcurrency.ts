import type { QueryClient } from "@tanstack/react-query";
import type { AuthLossReason } from "@/lib/auth/authLossReason";
import { enqueueAuthTelemetryEvent } from "@/lib/auth/authClientTelemetry";
import { meQueryKey } from "@/lib/auth/meQueryKey";

/** Single-flight auth redirects (SPA + hard navigation storms). */
let lastAuthRedirectAt = 0;
const AUTH_REDIRECT_COOLDOWN_MS = 2500;

export function tryScheduleAuthRedirect(run: () => void): boolean {
  if (typeof window === "undefined") return false;
  const now = Date.now();
  if (now - lastAuthRedirectAt < AUTH_REDIRECT_COOLDOWN_MS) return false;
  lastAuthRedirectAt = now;
  try {
    run();
  } catch {
    /* ignore */
  }
  return true;
}

/** Latest `/users/me` fetch generation — stale completions must not overwrite cache. */
let latestMeRequestSeq = 0;

export function beginMeRequest(): number {
  latestMeRequestSeq += 1;
  return latestMeRequestSeq;
}

export function isLatestMeRequest(seq: number): boolean {
  return seq === latestMeRequestSeq;
}

/**
 * Monotonic loss generation counter — never decreases (survives logical “recovery” for observability).
 * Pair with `authRecoveryVersion` to detect active loss without resetting the counter.
 */
let authLossVersion = 0;
/** Last acknowledged generation — when equal to `authLossVersion`, no active loss. */
let authRecoveryVersion = 0;
let lastAuthLossReason: AuthLossReason | null = null;
/** Epoch ms timestamps for observability and backend correlation payloads. */
let lastAuthLossAt: number | null = null;
let lastAuthRecoveryAt: number | null = null;

const concurrencyListeners = new Set<() => void>();

function emitConcurrency() {
  concurrencyListeners.forEach((l) => {
    try {
      l();
    } catch {
      /* ignore */
    }
  });
}

export function subscribeAuthConcurrency(cb: () => void): () => void {
  concurrencyListeners.add(cb);
  return () => concurrencyListeners.delete(cb);
}

export function getAuthLossVersion(): number {
  return authLossVersion;
}

export function getAuthLossVersionSnapshot(): number {
  return authLossVersion;
}

export function getAuthRecoveryVersion(): number {
  return authRecoveryVersion;
}

/** True when the latest loss generation has not been acknowledged by a successful `/users/me`. */
export function getAuthLossActive(): boolean {
  return authLossVersion > authRecoveryVersion;
}

export function getAuthLossActiveSnapshot(): boolean {
  return getAuthLossActive();
}

export function getLastAuthLossReason(): AuthLossReason | null {
  return lastAuthLossReason;
}

export function getLastAuthLossAt(): number | null {
  return lastAuthLossAt;
}

export function getLastAuthRecoveryAt(): number | null {
  return lastAuthRecoveryAt;
}

export function markAuthLossDetected(reason?: AuthLossReason | null): void {
  if (reason != null) {
    lastAuthLossReason = reason;
    recordAuthLoss(reason);
  }
  authLossVersion += 1;
  lastAuthLossAt = Date.now();
  emitConcurrency();
}

/** Call after a validated authenticated `/users/me` — acknowledges loss up to the current generation. */
export function clearAuthLossDetected(): void {
  if (!getAuthLossActive() && lastAuthLossReason == null) return;
  authRecoveryVersion = authLossVersion;
  lastAuthLossReason = null;
  lastAuthRecoveryAt = Date.now();
  emitConcurrency();
}

let clientAuthBootState = "UNKNOWN";

export function setClientAuthBootState(state: string): void {
  if (state === clientAuthBootState) return;
  clientAuthBootState = state;
}

export function getClientAuthBootState(): string {
  return clientAuthBootState;
}

/** Mirrors `useMe` identity refetch spinner — soft blocking tier (UI subtle busy, not axios mutation wall). */
let meIdentityRefreshing = false;

export function setMeIdentityRefreshingActive(on: boolean): void {
  if (meIdentityRefreshing === on) return;
  meIdentityRefreshing = on;
  emitConcurrency();
}

/**
 * Depth of identity refresh overlap when `/users/me` already had usable cache (mutation guard).
 * Clamped — mismatched leave/enter is logged rather than poisoning global state deeper.
 */
const ME_GUARD_MIN = 0;
const ME_GUARD_MAX = 8;
let meInteractionGuardDepth = ME_GUARD_MIN;
/** High-water mark for observable spikes (reset on navigation only via page reload clearing module — acceptable). */
let meInteractionGuardDepthMax = ME_GUARD_MIN;
const GUARD_SPIKE_THRESHOLD = 5;
const warnedGuardPeakDepths = new Set<number>();

export function enterMeInteractionGuard(): void {
  if (meInteractionGuardDepth >= ME_GUARD_MAX) {
    if (typeof console !== "undefined" && console.warn) {
      console.warn("[auth] meInteractionGuardDepth enter overflow — clamped", {
        depth: meInteractionGuardDepth,
        max: ME_GUARD_MAX,
      });
    }
    return;
  }
  meInteractionGuardDepth += 1;
  if (meInteractionGuardDepth > meInteractionGuardDepthMax) {
    meInteractionGuardDepthMax = meInteractionGuardDepth;
  }
  if (
    meInteractionGuardDepth >= GUARD_SPIKE_THRESHOLD &&
    !warnedGuardPeakDepths.has(meInteractionGuardDepth)
  ) {
    warnedGuardPeakDepths.add(meInteractionGuardDepth);
    enqueueAuthTelemetryEvent({ k: "guard_peak", depth: meInteractionGuardDepth, t: Date.now() });
    if (typeof console !== "undefined" && console.warn) {
      console.warn("[auth] meInteractionGuardDepth spike — depth=%s threshold=%s", meInteractionGuardDepth, GUARD_SPIKE_THRESHOLD);
    }
  }
  emitConcurrency();
}

export function leaveMeInteractionGuard(): void {
  if (meInteractionGuardDepth <= ME_GUARD_MIN) {
    if (typeof console !== "undefined" && console.warn) {
      console.warn("[auth] meInteractionGuardDepth leave underflow — ignored");
    }
    return;
  }
  meInteractionGuardDepth -= 1;
  emitConcurrency();
}

export function getMeInteractionGuardDepth(): number {
  return meInteractionGuardDepth;
}

export function getMeInteractionGuardDepthMax(): number {
  return meInteractionGuardDepthMax;
}

function normalizeMutationPathSegment(requestUrl: string): string {
  let u = String(requestUrl || "").trim();
  const query = u.indexOf("?");
  if (query >= 0) u = u.slice(0, query);
  if (!u.startsWith("/")) u = `/${u}`;
  return u.toLowerCase();
}

/** Only these POST/PUT/PATCH/DELETE prefixes may run during hard interaction blocks (loss / guard). */
const MUTATION_ALLOWLIST_PREFIXES = [
  "/auth/refresh/",
  "/auth/login/",
  "/auth/logout/",
  "/auth/csrf/",
  "/auth/client-telemetry/",
  "/users/google/",
  "/users/telegram/",
  "/users/register/",
] as const;

function isMutationAllowlisted(pathNormalized: string): boolean {
  for (const prefix of MUTATION_ALLOWLIST_PREFIXES) {
    if (pathNormalized === prefix.slice(0, -1) || pathNormalized.startsWith(prefix)) {
      return true;
    }
  }
  return false;
}

/** Hard: unresolved auth loss or overlapping guarded `/users/me` refresh (mutations must pause). */
export function globalHardInteractionBlockedSnapshot(): boolean {
  return getAuthLossActive() || meInteractionGuardDepth > 0;
}

/** Soft: identity refresh with warm cache — lighter UX only (does not block mutations). */
export function globalSoftInteractionBlockedSnapshot(): boolean {
  return meIdentityRefreshing;
}

/**
 * Packed snapshot for `useSyncExternalStore` (primitive stability).
 * bit0 = hard, bit1 = soft.
 */
export function getInteractionBlockedPackedSnapshot(): number {
  let n = 0;
  if (globalHardInteractionBlockedSnapshot()) n |= 1;
  if (globalSoftInteractionBlockedSnapshot()) n |= 2;
  return n;
}

/** Any deferral (hard ∪ soft) — used by critical gates that must wait for refetch too. */
export function globalInteractionBlockedSnapshot(): boolean {
  return getInteractionBlockedPackedSnapshot() !== 0;
}

export function shouldBlockMutatingRequests(method: string, requestUrl?: string): boolean {
  const m = method.toLowerCase();
  if (m === "get" || m === "head" || m === "options") return false;
  if (!globalHardInteractionBlockedSnapshot()) return false;

  const path = normalizeMutationPathSegment(String(requestUrl || ""));
  return !isMutationAllowlisted(path);
}

/** Lightweight counters for production debugging / external analytics hooks. */
export type AuthTelemetrySnapshot = {
  auth_loss_total: Record<AuthLossReason, number>;
  auth_refresh_total: number;
  auth_cancel_total: number;
  me_guard_depth_max: number;
  last_auth_loss_at: number | null;
  last_auth_recovery_at: number | null;
};

const authLossByReason: Record<AuthLossReason, number> = {
  EXPIRED: 0,
  NETWORK: 0,
  SERVER: 0,
  NO_SESSION: 0,
};

let authRefreshTotal = 0;
let authCancelTotal = 0;

export function recordAuthLoss(reason: AuthLossReason): void {
  authLossByReason[reason] = (authLossByReason[reason] ?? 0) + 1;
  enqueueAuthTelemetryEvent({ k: "loss", reason, t: Date.now() });
}

export function recordAuthRefresh(): void {
  authRefreshTotal += 1;
  enqueueAuthTelemetryEvent({ k: "refresh", t: Date.now() });
}

export function recordAuthCancel(): void {
  authCancelTotal += 1;
  enqueueAuthTelemetryEvent({ k: "cancel", t: Date.now() });
}

export function getAuthTelemetrySnapshot(): AuthTelemetrySnapshot {
  return {
    auth_loss_total: { ...authLossByReason },
    auth_refresh_total: authRefreshTotal,
    auth_cancel_total: authCancelTotal,
    me_guard_depth_max: meInteractionGuardDepthMax,
    last_auth_loss_at: lastAuthLossAt,
    last_auth_recovery_at: lastAuthRecoveryAt,
  };
}

export function installAuthTelemetryGlobal(): void {
  if (typeof window === "undefined") return;
  try {
    Object.defineProperty(window, "__MASTERSAT_AUTH_TELEMETRY__", {
      configurable: true,
      get: () => ({
        ...getAuthTelemetrySnapshot(),
        auth_loss_version: getAuthLossVersion(),
        auth_recovery_version: getAuthRecoveryVersion(),
        auth_loss_active: getAuthLossActive(),
        last_auth_loss_reason: getLastAuthLossReason(),
        last_auth_loss_at: getLastAuthLossAt(),
        last_auth_recovery_at: getLastAuthRecoveryAt(),
      }),
    });
  } catch {
    /* ignore */
  }
}

/** Canonical `/users/me` fetch with sequence guard + interaction depth for refresh cycles. */
export async function fetchMeWithConcurrency(
  queryClient: QueryClient,
  signal: AbortSignal | undefined,
  getMe: (opts?: { signal?: AbortSignal }) => Promise<unknown>,
): Promise<unknown> {
  const seq = beginMeRequest();
  const hadPrior = !!queryClient.getQueryData([...meQueryKey]);
  if (hadPrior) enterMeInteractionGuard();
  try {
    const data = await getMe({ signal });
    if (!isLatestMeRequest(seq)) {
      throw new DOMException("Stale me response", "AbortError");
    }
    return data;
  } finally {
    if (hadPrior) leaveMeInteractionGuard();
  }
}

/** Optional hook for mutations outside axios (e.g. fetch wrappers). */
export function criticalMutationAllowed(): boolean {
  return !globalHardInteractionBlockedSnapshot();
}
