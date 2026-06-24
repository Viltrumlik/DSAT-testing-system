"use client";

import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { AuthTabMessage } from "@/lib/auth/authTabSync";
import { markAuthLossDetected, tryScheduleAuthRedirect } from "@/lib/auth/authConcurrency";
import { invalidateMe } from "@/hooks/useMe";
import { clearAuthCookiesEverywhere, clearDerivedAuthProjectionCookies } from "@/lib/api";
import { meQueryKey } from "@/lib/auth/meQueryKey";
import { subscribeAuthTabSync } from "@/lib/auth/authTabSync";

/**
 * Sync auth across tabs:
 * `logout`: full cookie wipe + hard navigation to `/login` (matching `authApi.logout`).
 * `auth_lost`: passive session loss elsewhere — reconcile cache + projection then `/login`.
 *
 * On any tab signal, `/users/me` is cancelled + invalidated immediately (no waiting for navigation).
 */
export default function AuthTabSync() {
  const queryClient = useQueryClient();

  useEffect(() => {
    const onMsg = (msg: AuthTabMessage) => {
      if (msg.type === "auth_lost") {
        markAuthLossDetected(msg.reason);
      } else {
        markAuthLossDetected("NO_SESSION");
      }
      void invalidateMe(queryClient);

      if (msg.type === "auth_lost") {
        clearDerivedAuthProjectionCookies();
        queryClient.removeQueries({ queryKey: [...meQueryKey] });
        tryScheduleAuthRedirect(() => {
          try {
            if (window.location.pathname.startsWith("/login")) return;
            window.location.href = "/login";
          } catch {
            /* ignore */
          }
        });
        return;
      }
      clearDerivedAuthProjectionCookies();
      clearAuthCookiesEverywhere();
      queryClient.removeQueries({ queryKey: [...meQueryKey] });
      tryScheduleAuthRedirect(() => {
        try {
          if (window.location.pathname.startsWith("/login")) return;
          window.location.href = "/login";
        } catch {
          /* ignore */
        }
      });
    };

    return subscribeAuthTabSync(onMsg);
  }, [queryClient]);

  return null;
}
