"use client";

import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { invalidateMe } from "@/hooks/useMe";
import { getAuthLossActive, markAuthLossDetected } from "@/lib/auth/authConcurrency";
import { pushGlobalToastOnce } from "@/lib/toastBus";

/** React-only bridge for axios-level auth safeguards (circuit trip, reconciliation). */
export default function AuthResilienceSubscriber() {
  const queryClient = useQueryClient();
  const router = useRouter();

  useEffect(() => {
    const onCircuit = () => {
      pushGlobalToastOnce(
        "auth.circuit-trip",
        {
          tone: "error",
          message:
            "We couldn’t keep this tab aligned with your session on the server. Refreshing identity — sign in again if prompted.",
        },
        30_000,
      );
      if (!getAuthLossActive()) markAuthLossDetected("NETWORK");
      void invalidateMe(queryClient);
      try {
        router.refresh();
      } catch {
        /* ignore */
      }
    };
    window.addEventListener("mastersat-auth-circuit-trip", onCircuit);
    return () => window.removeEventListener("mastersat-auth-circuit-trip", onCircuit);
  }, [queryClient, router]);

  return null;
}
