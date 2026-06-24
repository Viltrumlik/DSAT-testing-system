"use client";
import { useCallback, useRef } from "react";
import type { Attempt } from "../types";

/**
 * Tracks the offset between the client clock and the server clock.
 *
 * The exam timer is server-authoritative: every attempt snapshot carries
 * `server_now`. By measuring `serverNow - Date.now()` on each fetch we can
 * compute "true" server time locally without trusting the device clock — which
 * defeats the trivial "set my clock back" bypass.
 */
export function useServerClock() {
  const offsetMsRef = useRef(0);

  /** Feed every fresh snapshot here to keep the offset calibrated. */
  const sync = useCallback((attempt: Pick<Attempt, "server_now"> | null | undefined) => {
    if (!attempt?.server_now) return;
    const serverMs = new Date(attempt.server_now).getTime();
    if (Number.isFinite(serverMs)) {
      offsetMsRef.current = serverMs - Date.now();
    }
  }, []);

  /** Current best estimate of server time, in ms. */
  const now = useCallback(() => Date.now() + offsetMsRef.current, []);

  return { sync, now, offsetMsRef };
}

export type ServerClock = ReturnType<typeof useServerClock>;
