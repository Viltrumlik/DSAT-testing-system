import {
  getAuthLossActive,
  getAuthLossVersion,
  getAuthRecoveryVersion,
  getClientAuthBootState,
  getLastAuthLossAt,
  getLastAuthLossReason,
  getLastAuthRecoveryAt,
  getMeInteractionGuardDepth,
} from "@/lib/auth/authConcurrency";

const ALLOWED_BOOT = new Set(["BOOTING", "AUTHENTICATED", "UNAUTHENTICATED"]);
const LOSS_REASONS = new Set(["EXPIRED", "NETWORK", "SERVER", "NO_SESSION"]);

const IS_PROD = process.env.NODE_ENV === "production";
const VERBOSE_HEADERS = process.env.NEXT_PUBLIC_MASTERSAT_AUTH_CORREL_HEADERS === "1";

function sanitizeBoot(state: string): string {
  if (state === "UNKNOWN") return "BOOTING";
  return ALLOWED_BOOT.has(state) ? state : "BOOTING";
}

/** Safe for untrusted log pipelines (omit raw monotonic counters in production unless opted-in). */
export function buildSanitizedAuthCorrelationHeaders(): Record<string, string> {
  const h: Record<string, string> = {
    "X-Mastersat-Auth-Boot": sanitizeBoot(getClientAuthBootState()),
    "X-Mastersat-Auth-Loss-Active": getAuthLossActive() ? "1" : "0",
    "X-Mastersat-Me-Guard-Depth": String(Math.min(8, Math.max(0, getMeInteractionGuardDepth()))),
  };
  if (!IS_PROD || VERBOSE_HEADERS) {
    h["X-Mastersat-Auth-Loss-Ver"] = String(getAuthLossVersion());
    h["X-Mastersat-Auth-Recovery-Ver"] = String(getAuthRecoveryVersion());
    const r = getLastAuthLossReason();
    if (r && LOSS_REASONS.has(r)) {
      h["X-Mastersat-Auth-Loss-Reason"] = r;
    }
    const la = getLastAuthLossAt();
    if (la != null) h["X-Mastersat-Auth-Loss-At"] = String(la);
    const ra = getLastAuthRecoveryAt();
    if (ra != null) h["X-Mastersat-Auth-Recovery-At"] = String(ra);
  }
  return h;
}
