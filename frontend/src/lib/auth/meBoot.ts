import type { AxiosError } from "axios";

export type AuthBootState = "BOOTING" | "AUTHENTICATED" | "UNAUTHENTICATED";

/**
 * Axios/RQ abort – not a session failure; do not clear `lms_user` projection cookies.
 * Covers: axios cancel, TanStack cancel, `fetchMeWithConcurrency` stale-completion `AbortError`,
 * and generic DOMException `AbortError` from `signal.abort()`.
 */
export function meErrorIsBenignCancellation(err: unknown): boolean {
  const ax = err as AxiosError;
  if (ax?.code === "ERR_CANCELED") return true;
  if (err instanceof Error && err.name === "CanceledError") return true;
  if (typeof DOMException !== "undefined" && err instanceof DOMException && err.name === "AbortError") {
    return true;
  }
  if (err instanceof Error && err.name === "AbortError") return true;
  return false;
}

export function mePayloadValid(data: unknown): data is Record<string, unknown> & { id: number } {
  return !!data && typeof data === "object" && typeof (data as { id?: unknown }).id === "number";
}

/**
 * Map React Query observers to coarse boot gates. Errors (after retries) always become UNAUTHENTICATED —
 * there is no terminal `ERROR` boot state so the UI cannot get stuck waiting for retries.
 */
export function deriveAuthBootState(opts: {
  status: string;
  data: unknown;
  error: unknown | null | undefined;
}): AuthBootState {
  const { status, data, error } = opts;

  if (status === "error") {
    void error;
    return "UNAUTHENTICATED";
  }

  // Pending or success with cached `me` (e.g. background refetch) — avoid boot shell / cookie churn.
  if (mePayloadValid(data)) return "AUTHENTICATED";

  if (status === "pending") return "BOOTING";

  if (status === "success") {
    return "UNAUTHENTICATED";
  }

  return "BOOTING";
}
