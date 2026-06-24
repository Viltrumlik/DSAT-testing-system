"use client";
import { Maximize } from "lucide-react";

interface FullscreenWarningProps {
  onReturn: () => void;
  /** Seconds left before the student is removed from the test (undefined hides it). */
  secondsLeft?: number;
}

/**
 * Blocking overlay shown when the student leaves full screen during an active
 * test (item: Forced Fullscreen). Re-entering requires a user gesture, so the
 * primary action is a button that calls requestFullscreen again. A countdown
 * warns that not returning will remove them from the test (the runner saves
 * progress and exits when it reaches zero).
 *
 * No backdrop blur — that caused a GPU-compositing flash during the native
 * fullscreen transition. The runner also gates this behind a short grace window
 * so it never flickers on a transient exit/re-enter.
 */
export function FullscreenWarning({ onReturn, secondsLeft }: FullscreenWarningProps) {
  return (
    <div
      role="alertdialog"
      aria-modal="true"
      aria-label="Full screen required"
      className="fixed inset-0 z-[80] flex items-center justify-center bg-slate-900/80 px-6"
    >
      <div className="w-full max-w-md rounded-2xl bg-white p-8 text-center shadow-2xl">
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-blue-50">
          <Maximize className="h-6 w-6 text-blue-700" />
        </div>
        <h2 className="mt-4 text-xl font-bold tracking-tight text-slate-900">Return to full screen</h2>
        <p className="mt-2 text-sm font-medium text-slate-500">
          This test must be taken in full screen. You exited full screen — your timer is still running.
        </p>

        {typeof secondsLeft === "number" && (
          <div
            className="mt-5 rounded-xl border border-red-200 bg-red-50 px-4 py-3"
            role="timer"
            aria-live="assertive"
          >
            <p className="text-sm font-semibold text-red-800">
              You’ll be removed from the test in{" "}
              <span className="tabular-nums">{Math.max(0, secondsLeft)}</span>{" "}
              {Math.max(0, secondsLeft) === 1 ? "second" : "seconds"}.
            </p>
            <p className="mt-0.5 text-xs text-red-600">Your answers are saved — you can resume where you left off.</p>
          </div>
        )}

        <button
          type="button"
          onClick={onReturn}
          className="mt-6 inline-flex w-full items-center justify-center gap-2 rounded-full bg-blue-700 px-6 py-3 text-base font-bold text-white transition-colors hover:bg-blue-800"
        >
          <Maximize className="h-5 w-5" />
          Return to full screen
        </button>
      </div>
    </div>
  );
}
