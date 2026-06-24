"use client";
import { useCallback, useRef, useState } from "react";
import { isAxiosError } from "axios";
import { type Attempt, InvalidAttemptPayloadError, parseAttempt } from "../types";
import { examApi } from "../services/examApiClient";
import { clearDraft } from "../services/draftStore";
import { submitKey } from "../utils/idempotency";

interface UseModuleSubmitArgs {
  attemptId: number;
  attempt: Attempt | null;
  answers: Record<string, string>;
  flagged: number[];
  applyAttempt: (next: Attempt) => void;
  assertCriticalAuth: () => boolean;
}

interface UseModuleSubmitResult {
  submit: () => Promise<void>;
  submitting: boolean;
  /** Non-null when a submit ultimately failed; the student can retry via `submit`. */
  submitError: string | null;
  clearSubmitError: () => void;
}

const WATCHDOG_MS = 5000;
const MAX_RETRIES = 4;

/**
 * Submits the active module with full safety:
 *  - submission lock (no double submit, even with the timer + a click racing);
 *  - idempotency key + `expected_version_number` (server dedupes / rejects stale);
 *  - 409 conflict reconciliation (adopt the server's attempt; retry once if still on M1);
 *  - watchdog (if the request hangs, poll status to see if it already landed);
 *  - bounded exponential-backoff retry on transient failures.
 */
export function useModuleSubmit({
  attemptId,
  attempt,
  answers,
  flagged,
  applyAttempt,
  assertCriticalAuth,
}: UseModuleSubmitArgs): UseModuleSubmitResult {
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const lockRef = useRef(false);

  // `submit` closes over the current props and is recreated when they change.
  // That's safe for the auto-submit path because `useModuleTimer` stores its
  // `onExpire` callback in a ref, so a new `submit` identity never restarts the
  // timer — it just means expiry always fires the freshest closure.
  const submit = useCallback(async () => {
    const current = attempt;
    const ans = answers;
    const flg = flagged;
    if (!current?.current_module_details) return;
    if (lockRef.current) return;
    if (!assertCriticalAuth()) return;

    lockRef.current = true;
    setSubmitting(true);
    setSubmitError(null);

    const moduleId = current.current_module_details.id;
    const baseVersion = current.version_number;
    const key = submitKey(attemptId, moduleId, baseVersion);

    let settled = false;
    const finish = (snap?: Attempt) => {
      if (settled) return;
      settled = true;
      if (snap) {
        applyAttempt(snap);
        if (snap.current_module_details?.id !== moduleId) clearDraft(attemptId, moduleId);
      }
      lockRef.current = false;
      setSubmitting(false);
    };

    // Watchdog: if the POST hangs, see whether the backend already advanced.
    const watchdog = setTimeout(async () => {
      try {
        const snap = await examApi.getStatus(attemptId);
        if (snap.version_number > baseVersion || snap.is_completed || snap.current_state === "SCORING") {
          finish(snap);
        }
      } catch {
        /* ignore; the main path will surface errors */
      }
    }, WATCHDOG_MS);

    const attemptSubmit = async (retry = 0): Promise<void> => {
      if (settled) return;
      try {
        const snap = await examApi.submitModule(attemptId, ans, flg, {
          idempotencyKey: retry === 0 ? key : `${key}.r${retry}`,
          expectedVersionNumber: baseVersion,
        });
        finish(snap);
      } catch (err) {
        const status = isAxiosError(err) ? err.response?.status : undefined;

        // 409: the server is ahead. Adopt its attempt; if still on M1, retry once.
        if (status === 409 && isAxiosError(err)) {
          const body = err.response?.data;
          const rawAttempt =
            body && typeof body === "object" && "attempt" in body ? (body as { attempt: unknown }).attempt : null;
          if (rawAttempt) {
            try {
              const conflict = parseAttempt(rawAttempt, "submit 409 body");
              applyAttempt(conflict);
              if (conflict.current_state === "MODULE_1_ACTIVE" && retry === 0) {
                const snap2 = await examApi.submitModule(attemptId, ans, flg, {
                  idempotencyKey: `${submitKey(attemptId, conflict.current_module_details?.id ?? moduleId, conflict.version_number)}.retry`,
                  expectedVersionNumber: conflict.version_number,
                });
                finish(snap2);
                return;
              }
              finish(conflict);
              return;
            } catch (e) {
              if (e instanceof InvalidAttemptPayloadError) console.error(e);
            }
          }
        }

        // Transient failure: bounded backoff, unless the watchdog already recovered.
        if (!settled && retry < MAX_RETRIES) {
          setTimeout(() => void attemptSubmit(retry + 1), 2 ** retry * 1000);
          return;
        }
        // Last resort: one status check. ONLY treat it as success if the attempt
        // actually advanced — a 200 that still shows the same module means the
        // submit never landed, and silently finishing would strand the student
        // on a "submitted" exam that didn't move.
        try {
          const snap = await examApi.getStatus(attemptId);
          if (snap.version_number > baseVersion || snap.is_completed || snap.current_state === "SCORING") {
            finish(snap);
            return;
          }
          applyAttempt(snap); // keep local state fresh, but the submit didn't take
        } catch {
          /* fall through to surface a retryable error */
        }
        // Recoverable: keep the student on the exam with their answers intact and
        // let them retry (available to everyone, not just admins). The retry is
        // idempotent — same (attempt, module, version) key, so it can't double-submit.
        settled = true;
        clearTimeout(watchdog);
        lockRef.current = false;
        setSubmitting(false);
        setSubmitError(`Submit failed.${status ? ` (HTTP ${status})` : ""} Your answers are saved. Please try again.`);
      }
    };

    await attemptSubmit();
    clearTimeout(watchdog);
  }, [attemptId, attempt, answers, flagged, applyAttempt, assertCriticalAuth]);

  return { submit, submitting, submitError, clearSubmitError: useCallback(() => setSubmitError(null), []) };
}
