"use client";
import { Clock, ListChecks, Maximize, Play } from "lucide-react";
import { SatColorRule } from "./SatColorRule";

interface WelcomeScreenProps {
  /** e.g. "Section 1, Module 1: Reading and Writing". */
  moduleTitle: string;
  /** "Reading and Writing" | "Math" — used in the prose line. */
  subjectLabel: string;
  /** Whole minutes available for this module (0/undefined hides the line). */
  minutes?: number;
  /** Question count (undefined hides the line until known). */
  questionCount?: number;
  /** True while the start request is in flight. */
  starting: boolean;
  /** Whether fullscreen will be requested on start (drives the helper text). */
  fullscreenSupported: boolean;
  onStart: () => void;
}

/**
 * Bluebook-style start screen shown before a module's timer begins. The clock
 * does NOT start until the student clicks Start — the runner defers the engine
 * `start()` call to this button (which is also the user gesture used to enter
 * fullscreen). Shown only for a NOT_STARTED attempt; resumes skip it.
 */
export function WelcomeScreen({
  moduleTitle,
  subjectLabel,
  minutes,
  questionCount,
  starting,
  fullscreenSupported,
  onStart,
}: WelcomeScreenProps) {
  return (
    <div className="flex h-screen flex-col bg-white">
      <SatColorRule />
      <div className="flex flex-1 items-center justify-center px-6">
        <div className="w-full max-w-lg rounded-3xl border border-slate-200 bg-white p-10 text-center shadow-sm">
          <p className="text-xs font-bold uppercase tracking-[0.2em] text-blue-700">Practice Test</p>
          <h1 className="mt-3 text-2xl font-bold tracking-tight text-slate-900">{moduleTitle}</h1>
          <p className="mt-2 text-sm font-medium text-slate-500">
            When you’re ready, start the {subjectLabel} module below.
          </p>

          <div className="mt-7 grid grid-cols-2 gap-3">
            <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
              <Clock className="mx-auto h-5 w-5 text-slate-500" />
              <div className="mt-2 text-lg font-bold text-slate-900">
                {minutes ? `${minutes} min` : "—"}
              </div>
              <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">Time</div>
            </div>
            <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
              <ListChecks className="mx-auto h-5 w-5 text-slate-500" />
              <div className="mt-2 text-lg font-bold text-slate-900">
                {questionCount ? questionCount : "—"}
              </div>
              <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">Questions</div>
            </div>
          </div>

          <ul className="mt-6 space-y-2 text-left text-sm text-slate-600">
            <li className="flex gap-2"><span className="text-blue-600">•</span> The timer starts when you press Start and cannot be reset.</li>
            <li className="flex gap-2"><span className="text-blue-600">•</span> You can flag questions for review and return to them before submitting.</li>
            <li className="flex gap-2"><span className="text-blue-600">•</span> Your answers save automatically as you go.</li>
            {fullscreenSupported && (
              <li className="flex gap-2"><span className="text-blue-600">•</span> The test opens in full screen — stay in full screen until you finish.</li>
            )}
          </ul>

          <button
            type="button"
            onClick={onStart}
            disabled={starting}
            className="mt-8 inline-flex w-full items-center justify-center gap-2 rounded-full bg-blue-700 px-8 py-3 text-base font-bold text-white transition-colors hover:bg-blue-800 disabled:opacity-60"
          >
            {fullscreenSupported ? <Maximize className="h-5 w-5" /> : <Play className="h-5 w-5" />}
            {starting ? "Starting…" : "Start"}
          </button>
        </div>
      </div>
      <SatColorRule />
    </div>
  );
}
