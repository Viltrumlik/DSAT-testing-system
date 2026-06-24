"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { type Attempt, ATTEMPT_STATE, InvalidAttemptPayloadError } from "../types";
import { examApi } from "../services/examApiClient";
import { isScoring, mergeAttempt } from "../state/attemptMerge";
import { startKey } from "../utils/idempotency";
import { useServerClock } from "./useServerClock";

interface UseExamAttemptArgs {
  attemptId: number;
  /** Gate that blocks engine mutations while auth is being revalidated. */
  assertCriticalAuth: () => boolean;
  /** When false, the background polling loop is suspended (e.g. a blocked duplicate tab). */
  pollingEnabled?: boolean;
  /**
   * When false, a NOT_STARTED attempt is NOT auto-started on load — the timer
   * stays unstarted until `start()` is called (driven by the Welcome screen's
   * Start button). Defaults to true to preserve the legacy auto-start flow.
   */
  autoStart?: boolean;
}

export interface UseExamAttemptResult {
  attempt: Attempt | null;
  loading: boolean;
  error: string | null;
  clock: ReturnType<typeof useServerClock>;
  /** Merge a snapshot we already hold (e.g. a submit/pause response) into state. */
  applyAttempt: (next: Attempt) => void;
  /** Hard reload from the server (used by the Retry button). */
  reload: () => void;
  setError: (msg: string | null) => void;
  /** Transition NOT_STARTED → MODULE_1_ACTIVE on demand (Welcome screen Start). */
  start: () => Promise<void>;
}

/**
 * Owns the authoritative `Attempt` snapshot: initial load + engine start,
 * background polling while active, and fast polling while SCORING. All writes
 * go through `applyAttempt`, which enforces the forward-only merge guard and
 * recalibrates the server clock.
 */
export function useExamAttempt({ attemptId, assertCriticalAuth, pollingEnabled = true, autoStart = true }: UseExamAttemptArgs): UseExamAttemptResult {
  const clock = useServerClock();
  const [attempt, setAttempt] = useState<Attempt | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadNonce, setReloadNonce] = useState(0);

  const attemptRef = useRef<Attempt | null>(null);
  attemptRef.current = attempt;

  const applyAttempt = useCallback(
    (next: Attempt) => {
      clock.sync(next);
      setAttempt((prev) => mergeAttempt(prev, next));
    },
    [clock],
  );

  const reload = useCallback(() => {
    setError(null);
    setLoading(true);
    setAttempt(null);
    setReloadNonce((n) => n + 1);
  }, []);

  // On-demand engine start (Welcome screen). Idempotent via the start key, so a
  // double click can't create two starts; the timer anchors from the server's
  // post-start snapshot.
  const start = useCallback(async () => {
    if (!assertCriticalAuth()) return;
    try {
      const snap = await examApi.start(attemptId, startKey(attemptId));
      applyAttempt(snap);
    } catch (e) {
      if (e instanceof InvalidAttemptPayloadError) console.error(e);
    }
    try {
      applyAttempt(await examApi.getStatus(attemptId));
    } catch {
      /* background polling will reconcile */
    }
  }, [attemptId, assertCriticalAuth, applyAttempt]);

  // ── Initial load (+ engine start for NOT_STARTED) ──────────────────────────
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        setError(null);
        let snap = await examApi.getStatus(attemptId);
        if (cancelled) return;
        applyAttempt(snap);

        if (autoStart && snap.current_state === ATTEMPT_STATE.NOT_STARTED) {
          if (!assertCriticalAuth()) {
            setLoading(false);
            return;
          }
          try {
            snap = await examApi.start(attemptId, startKey(attemptId));
            if (!cancelled) applyAttempt(snap);
          } catch (e) {
            if (e instanceof InvalidAttemptPayloadError) console.error(e);
          }
          snap = await examApi.getStatus(attemptId);
          if (cancelled) return;
          applyAttempt(snap);
        }

        if (snap.is_expired && !snap.is_completed) {
          setError("Your time on this module has elapsed. Click Retry to sync and continue.");
        }
      } catch (e) {
        if (cancelled) return;
        if (e instanceof InvalidAttemptPayloadError) console.error(e);
        setError("Could not load the exam. Please click Retry.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [attemptId, reloadNonce]);

  // ── Background poll: active modules (slow) and SCORING (fast) ───────────────
  useEffect(() => {
    if (!pollingEnabled) return; // suspended for blocked duplicate tabs
    const state = attempt?.current_state;
    if (!state || state === ATTEMPT_STATE.COMPLETED) return;

    const scoring = isScoring(attempt);
    const baseDelay = scoring ? 1200 : 10_000;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let delay = baseDelay;

    const tick = async () => {
      try {
        const snap = await examApi.getStatus(attemptId);
        if (cancelled) return; // discard stale in-flight response
        applyAttempt(snap);
        if (snap.is_expired && !snap.is_completed) {
          setError("This module has expired. Please click Retry to sync.");
          return;
        }
        delay = baseDelay;
      } catch (e) {
        if (e instanceof InvalidAttemptPayloadError) console.error(e);
        delay = Math.min(30_000, Math.floor(delay * 1.6)); // back off on failure
      }
      if (!cancelled) timer = setTimeout(tick, delay);
    };

    timer = setTimeout(tick, scoring ? 600 : 5000);
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [attempt?.current_state, attemptId, pollingEnabled]);

  return { attempt, loading, error, clock, applyAttempt, reload, setError, start };
}
