export type MastersatToastDetail = {
  tone?: "neutral" | "success" | "error";
  message: string;
};

const toastDedupeLastAt = new Map<string, number>();

/** Dispatches to `ToastProvider` without React context (axios / auth libs). */
export function pushGlobalToast(payload: MastersatToastDetail): void {
  if (typeof window === "undefined") return;
  try {
    window.dispatchEvent(new CustomEvent("mastersat-toast", { detail: payload }));
  } catch {
    /* ignore */
  }
}

/**
 * Same as `pushGlobalToast`, but at most once per `windowMs` per key (e.g. repeated temporal-stale storms).
 */
export function pushGlobalToastOnce(
  dedupeKey: string,
  payload: MastersatToastDetail,
  windowMs: number = 15_000,
): void {
  if (typeof window === "undefined") return;
  const now = Date.now();
  const last = toastDedupeLastAt.get(dedupeKey) ?? 0;
  if (now - last < windowMs) return;
  toastDedupeLastAt.set(dedupeKey, now);
  pushGlobalToast(payload);
}

export function clearGlobalToastDedupForTests(): void {
  toastDedupeLastAt.clear();
}
