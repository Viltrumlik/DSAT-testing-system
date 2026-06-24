"use client";
import { useEffect, useRef, useState } from "react";
import type { Attempt } from "../types";
import { moduleLimitSeconds } from "../utils/time";
import type { ServerClock } from "./useServerClock";

interface UseModuleTimerArgs {
  attempt: Attempt | null;
  clock: ServerClock;
  /** When true the countdown freezes (manual pause). */
  paused: boolean;
  /** Fired exactly once per module when the clock reaches zero. */
  onExpire: () => void;
}

interface UseModuleTimerResult {
  /** Whole seconds remaining in the active module. */
  secondsLeft: number;
  /** True once anchored to a real module — gates auto-submit so it can't fire on 0/unloaded. */
  ready: boolean;
}

/**
 * Server-anchored module countdown.
 *
 * Design (replaces the legacy 5-effect / 6-ref timer):
 *  - Anchors a `deadline` in *server time* (`clock.now() + remaining*1000`) once
 *    per module. The display is derived from `deadline - serverNow`, so it never
 *    drifts with React renders and can't be sped up by the device clock.
 *  - Re-anchors ONLY when the module identity changes — never on a routine poll,
 *    so background `remaining_seconds` updates don't make the display jump.
 *  - Pause freezes by snapshotting the remaining time; resume re-anchors from it.
 *  - Calls `onExpire` once per module via a latch ref.
 */
export function useModuleTimer({ attempt, clock, paused, onExpire }: UseModuleTimerArgs): UseModuleTimerResult {
  const [secondsLeft, setSecondsLeft] = useState(0);
  const [ready, setReady] = useState(false);

  const deadlineRef = useRef(0); // server-time ms when the module hits 0
  const expiredLatchRef = useRef(false); // ensures onExpire fires once per module
  const pausedRef = useRef(paused);
  const frozenRef = useRef<number | null>(null); // remaining secs captured at pause
  const onExpireRef = useRef(onExpire);
  onExpireRef.current = onExpire;

  const moduleId = attempt?.current_module_details?.id ?? null;
  const startTime = attempt?.current_module_start_time ?? null;
  const limitSeconds = attempt
    ? moduleLimitSeconds({
        module_duration_seconds: attempt.module_duration_seconds,
        time_limit_minutes: attempt.current_module_details?.time_limit_minutes,
      })
    : 0;

  // (Re)anchor when the module identity changes.
  useEffect(() => {
    if (!moduleId || !startTime || limitSeconds <= 0) {
      setReady(false);
      return;
    }
    const serverRemaining =
      attempt?.remaining_seconds != null && Number.isFinite(attempt.remaining_seconds)
        ? Math.max(0, Math.floor(attempt.remaining_seconds))
        : (() => {
            const startMs = new Date(startTime).getTime();
            if (!Number.isFinite(startMs)) return limitSeconds;
            return Math.max(0, limitSeconds - Math.floor((clock.now() - startMs) / 1000));
          })();

    deadlineRef.current = clock.now() + serverRemaining * 1000;
    expiredLatchRef.current = false;
    frozenRef.current = null;
    setSecondsLeft(serverRemaining);
    setReady(true);
    // Intentionally keyed on module identity only — see hook docblock.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [moduleId, startTime, limitSeconds]);

  // Pause / resume re-anchoring.
  useEffect(() => {
    const was = pausedRef.current;
    pausedRef.current = paused;
    if (!ready) return;
    if (paused && !was) {
      // Entering pause: snapshot remaining.
      frozenRef.current = Math.max(0, Math.ceil((deadlineRef.current - clock.now()) / 1000));
    } else if (!paused && was && frozenRef.current != null) {
      // Resuming: rebuild deadline from the frozen value (no wall-clock jump).
      deadlineRef.current = clock.now() + frozenRef.current * 1000;
      frozenRef.current = null;
    }
  }, [paused, ready, clock]);

  // The tick loop: one rAF, but only commits state on whole-second changes.
  useEffect(() => {
    if (!ready) return;
    let raf = 0;
    let lastRendered = -1;

    const loop = () => {
      if (pausedRef.current) {
        raf = requestAnimationFrame(loop);
        return;
      }
      const remaining = Math.max(0, Math.ceil((deadlineRef.current - clock.now()) / 1000));
      if (remaining !== lastRendered) {
        lastRendered = remaining;
        setSecondsLeft(remaining);
      }
      if (remaining <= 0) {
        if (!expiredLatchRef.current) {
          expiredLatchRef.current = true;
          onExpireRef.current();
        }
        return; // stop — module is over
      }
      raf = requestAnimationFrame(loop);
    };

    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [ready, moduleId, clock]);

  return { secondsLeft, ready };
}
