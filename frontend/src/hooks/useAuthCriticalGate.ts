"use client";

import { useMemo, useCallback, useSyncExternalStore } from "react";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { getAuthLossActiveSnapshot, subscribeAuthConcurrency, tryScheduleAuthRedirect } from "@/lib/auth/authConcurrency";
import { invalidateMe, useMe } from "@/hooks/useMe";

/**
 * Blocks exam / homework / assessment mutations while identity is being revalidated or emergency auth-loss is active.
 */
export function useAuthCriticalGate() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { bootState, isAuthenticated, globalInteractionBlocked } = useMe();

  const authLossEmergency = useSyncExternalStore(subscribeAuthConcurrency, getAuthLossActiveSnapshot, () => false);

  const criticalAuthReady = useMemo(
    () => bootState === "AUTHENTICATED" && isAuthenticated && !globalInteractionBlocked,
    [bootState, isAuthenticated, globalInteractionBlocked],
  );

  const assertCriticalAuth = useCallback(() => {
    if (!criticalAuthReady) {
      tryScheduleAuthRedirect(() => {
        void invalidateMe(queryClient);
        router.push("/login");
      });
      return false;
    }
    return true;
  }, [criticalAuthReady, queryClient, router]);

  return {
    assertCriticalAuth,
    criticalAuthReady,
    bootState,
    isAuthenticated,
    authLossEmergency,
    globalInteractionBlocked,
  };
}
