import type { AxiosError } from "axios";
import { meErrorIsBenignCancellation, mePayloadValid } from "@/lib/auth/meBoot";

/** Why `/users/me` is not yielding a usable session (UX + multi-tab payloads). */
export type AuthLossReason = "EXPIRED" | "NETWORK" | "SERVER" | "NO_SESSION";

const REASON_SET = new Set<AuthLossReason>(["EXPIRED", "NETWORK", "SERVER", "NO_SESSION"]);

export function isAuthLossReason(x: unknown): x is AuthLossReason {
  return typeof x === "string" && REASON_SET.has(x as AuthLossReason);
}

function classifyAxiosToReason(error: unknown): AuthLossReason {
  const ax = error as AxiosError;
  const s = ax.response?.status;
  if (s === 401 || s === 403) return "EXPIRED";
  if (s !== undefined && s >= 500) return "SERVER";
  if (s !== undefined && s >= 400) return "NO_SESSION";

  const code = ax.code as string | undefined;
  if (code === "ECONNABORTED" || code === "ETIMEDOUT") return "NETWORK";
  if (!ax.response) return "NETWORK";

  return "NETWORK";
}

/**
 * Resolved reason for debug / banners from the canonical `me` query snapshot.
 * `null` means no failure semantics (authenticated, still loading, or benign cancel noise).
 */
export function classifyAuthLossReason(opts: {
  queryStatus: "pending" | "error" | "success";
  data: unknown;
  error: unknown;
}): AuthLossReason | null {
  const { queryStatus, data, error } = opts;
  if (queryStatus === "pending") return null;
  if (queryStatus === "success") {
    return mePayloadValid(data) ? null : "NO_SESSION";
  }
  if (meErrorIsBenignCancellation(error)) return null;
  return classifyAxiosToReason(error);
}
