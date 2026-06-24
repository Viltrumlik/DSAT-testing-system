"use client";
import { ChevronUp } from "lucide-react";

interface ExamFooterProps {
  navLabel: string;
  onToggleNavigator: () => void;
  canGoBack: boolean;
  onBack: () => void;
  isLastQuestion: boolean;
  onNext: () => void;
  onSubmitModule: () => void;
  submitting: boolean;
  /** Student identity — shown at the bottom-left throughout the test. */
  studentName?: string;
  /** When true, Back/Next are briefly locked (anti double-click). */
  navLocked?: boolean;
}

/** Bottom bar: student identity + question-grid toggle + Back / Next / Submit. */
export function ExamFooter({
  navLabel,
  onToggleNavigator,
  canGoBack,
  onBack,
  isLastQuestion,
  onNext,
  onSubmitModule,
  submitting,
  studentName,
  navLocked = false,
}: ExamFooterProps) {
  return (
    <footer className="flex shrink-0 items-center justify-between bg-slate-50 px-6 py-3">
      {/* Left: persistent student identity. */}
      <div className="flex flex-1 items-center">
        {studentName ? (
          <span className="truncate text-sm font-semibold text-slate-600" title={studentName}>
            {studentName}
          </span>
        ) : null}
      </div>

      {/* Center: the question-navigator pill (Bluebook-style rounded pill). */}
      <button
        type="button"
        onClick={onToggleNavigator}
        aria-haspopup="dialog"
        className="inline-flex items-center gap-2 rounded-full bg-slate-900 px-5 py-2 text-sm font-bold text-white shadow-sm transition-colors hover:bg-slate-800"
      >
        {navLabel}
        <ChevronUp className="h-4 w-4" />
      </button>

      {/* Right: Back (secondary/outlined) + Next/Submit (primary). */}
      <div className="flex flex-1 items-center justify-end gap-3">
        <button
          type="button"
          onClick={onBack}
          disabled={!canGoBack || navLocked}
          className="rounded-full border border-slate-300 bg-white px-6 py-2 text-sm font-bold text-slate-700 transition-colors hover:border-slate-400 disabled:opacity-40"
        >
          Back
        </button>
        {isLastQuestion ? (
          <button
            type="button"
            onClick={onSubmitModule}
            disabled={submitting || navLocked}
            className="rounded-full bg-blue-700 px-7 py-2 text-sm font-bold text-white shadow-sm transition-colors hover:bg-blue-800 disabled:opacity-50"
          >
            {submitting ? "Submitting…" : "Submit"}
          </button>
        ) : (
          <button
            type="button"
            onClick={onNext}
            disabled={navLocked}
            className="rounded-full bg-blue-700 px-7 py-2 text-sm font-bold text-white shadow-sm transition-colors hover:bg-blue-800 disabled:opacity-60"
          >
            Next
          </button>
        )}
      </div>
    </footer>
  );
}
