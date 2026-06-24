import Cookies from "js-cookie";
import type { AuthLossReason } from "@/lib/auth/authLossReason";
import { isAuthLossReason } from "@/lib/auth/authLossReason";

/** Broadcast + storage ping for logout / passive auth loss. */
export const AUTH_TAB_STORAGE_KEY = "mastersat_auth_tab_v1";

/** Login page: persisted notice consumed once (`localStorage`). */
export const AUTH_NOTICE_STORAGE_KEY = "mastersat_auth_notice_v1";

/** v1 legacy (no user scoping); v2 includes `user_id` for shared-browser safety. */
export type AuthNoticeRecord =
  | { v: 1; at: number; reason: AuthLossReason }
  | { v: 2; at: number; reason: AuthLossReason; user_id: number | null };

export type AuthTabMessage =
  | { type: "logout"; at: number }
  | { type: "auth_lost"; at: number; reason: AuthLossReason; user_id?: number | null };

let bc: BroadcastChannel | null = null;

function getBc(): BroadcastChannel | null {
  if (typeof window === "undefined") return null;
  if (bc) return bc;
  try {
    bc = new BroadcastChannel("mastersat-auth-v1");
    return bc;
  } catch {
    return null;
  }
}

function postToStorage(msg: AuthTabMessage): void {
  try {
    localStorage.setItem(AUTH_TAB_STORAGE_KEY, JSON.stringify(msg));
  } catch {
    /* quota / private mode */
  }
}

function postLogout(msg: AuthTabMessage): void {
  const ch = getBc();
  if (ch) {
    try {
      ch.postMessage(msg);
    } catch {
      /* ignore */
    }
  }
  postToStorage(msg);
}

/** User-initiated logout (server clears session; other tabs sync). */
export function broadcastLogoutToOtherTabs(): void {
  if (typeof window === "undefined") return;
  postLogout({ type: "logout", at: Date.now() });
}

/**
 * Passive session loss. Uses **storage only** so the originating tab doesn't receive storage events.
 * Optional `user_id` helps peers correlate which identity was dropped.
 */
export function broadcastAuthLostToOtherTabs(reason: AuthLossReason, userId: number | null): void {
  if (typeof window === "undefined") return;
  postToStorage({
    type: "auth_lost",
    at: Date.now(),
    reason,
    user_id: userId,
  });
}

export function persistAuthNotice(reason: AuthLossReason, userId: number | null): void {
  const rec: AuthNoticeRecord = { v: 2, at: Date.now(), reason, user_id: userId };
  try {
    localStorage.setItem(AUTH_NOTICE_STORAGE_KEY, JSON.stringify(rec));
  } catch {
    /* ignore */
  }
}

function readProjectionUserId(): number | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = Cookies.get("lms_user");
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { id?: unknown };
    const id = parsed?.id;
    return typeof id === "number" && Number.isFinite(id) ? id : null;
  } catch {
    return null;
  }
}

/** Read + atomically remove. Drops notices scoped to another user (`lms_user.id` mismatch). */
export function consumeAuthNotice(): AuthNoticeRecord | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(AUTH_NOTICE_STORAGE_KEY);
    if (!raw) return null;
    localStorage.removeItem(AUTH_NOTICE_STORAGE_KEY);
    const parsed = JSON.parse(raw) as Partial<AuthNoticeRecord> & { v?: unknown; user_id?: unknown };
    const at = parsed.at;
    if (typeof at !== "number") return null;
    if (!isAuthLossReason(parsed.reason)) return null;

    const projId = readProjectionUserId();

    if (parsed.v === 1) {
      return { v: 1, at, reason: parsed.reason };
    }
    if (parsed.v === 2) {
      const uidRaw = parsed.user_id;
      const user_id =
        uidRaw === null || uidRaw === undefined
          ? null
          : typeof uidRaw === "number" && Number.isFinite(uidRaw)
            ? uidRaw
            : null;

      if (user_id !== null && projId !== null && user_id !== projId) {
        return null;
      }
      return { v: 2, at, reason: parsed.reason, user_id };
    }

    return null;
  } catch {
    return null;
  }
}

function parseAuthTabMessage(raw: unknown): AuthTabMessage | null {
  if (!raw || typeof raw !== "object") return null;
  const d = raw as { type?: unknown; at?: unknown; reason?: unknown; user_id?: unknown };
  if (typeof d.at !== "number") return null;
  if (d.type === "logout") return { type: "logout", at: d.at };
  if (d.type === "auth_lost" && isAuthLossReason(d.reason)) {
    const uid = d.user_id;
    let user_id: number | null | undefined;
    if (uid === undefined) user_id = undefined;
    else if (uid === null) user_id = null;
    else if (typeof uid === "number" && Number.isFinite(uid)) user_id = uid;
    else return null;
    return { type: "auth_lost", at: d.at, reason: d.reason, user_id };
  }
  return null;
}

export function subscribeAuthTabSync(cb: (msg: AuthTabMessage) => void): () => void {
  if (typeof window === "undefined") return () => {};

  const ch = getBc();
  const onBc = (ev: MessageEvent<unknown>) => {
    const msg = parseAuthTabMessage(ev.data);
    if (msg) cb(msg);
  };
  ch?.addEventListener("message", onBc);

  const onStorage = (e: StorageEvent) => {
    if (e.key !== AUTH_TAB_STORAGE_KEY || !e.newValue) return;
    try {
      const msg = parseAuthTabMessage(JSON.parse(e.newValue));
      if (msg) cb(msg);
    } catch {
      /* ignore */
    }
  };
  window.addEventListener("storage", onStorage);

  return () => {
    ch?.removeEventListener("message", onBc);
    window.removeEventListener("storage", onStorage);
  };
}
