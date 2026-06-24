"use client";
import { ArrowLeft, Flag } from "lucide-react";
import type { ExamQuestion } from "../types";
import { SatColorRule } from "./SatColorRule";

interface CheckYourWorkPageProps {
  moduleTitle: string;
  questions: ExamQuestion[];
  answers: Record<string, string>;
  flagged: number[];
  /** Jump back to a specific question (closes this page). */
  onJump: (index: number) => void;
  /** Return to the last question without submitting. */
  onBack: () => void;
  /** Confirm + submit the module. */
  onSubmit: () => void;
  submitting: boolean;
  /** Drives the primary button label: last module finishes; otherwise continues. */
  isLastModule: boolean;
  studentName?: string;
}

/**
 * Official-style "Check Your Work" review page (item: Check Your Work Page).
 * Shown before a module is submitted: a status legend + a question grid the
 * student can jump from, and an explicit confirm button. Reached from the
 * footer's last-question action or the navigator's "Go to Review Page".
 */
export function CheckYourWorkPage({
  moduleTitle,
  questions,
  answers,
  flagged,
  onJump,
  onBack,
  onSubmit,
  submitting,
  isLastModule,
  studentName,
}: CheckYourWorkPageProps) {
  const answeredCount = questions.filter((q) => Boolean(answers[q.id])).length;
  const flaggedCount = questions.filter((q) => flagged.includes(q.id)).length;
  const unansweredCount = questions.length - answeredCount;

  return (
    <div className="flex h-screen flex-col bg-slate-50">
      <SatColorRule />
      <header className="flex shrink-0 items-center justify-between bg-white px-6 py-3">
        <button
          type="button"
          onClick={onBack}
          className="inline-flex items-center gap-1.5 text-sm font-bold text-blue-700 hover:text-blue-800"
        >
          <ArrowLeft className="h-4 w-4" /> Back to questions
        </button>
        <h1 className="text-base font-bold tracking-tight text-slate-900">{moduleTitle}</h1>
        <div className="w-32" />
      </header>

      <main className="flex flex-1 items-center justify-center overflow-y-auto px-6 py-8">
        <div className="w-full max-w-4xl rounded-3xl border border-slate-200 bg-white p-8 shadow-sm">
          <div className="mb-6 flex flex-wrap items-end justify-between gap-2">
            <h2 className="text-2xl font-bold tracking-tight text-slate-900">Question Navigator</h2>
            <p className="text-sm font-medium text-slate-500">Click any question to review your answer</p>
          </div>

          <div className="grid grid-cols-6 gap-3 sm:grid-cols-9 lg:grid-cols-12">
            {questions.map((q, i) => {
              const answered = Boolean(answers[q.id]);
              const isFlagged = flagged.includes(q.id);
              const base =
                "relative flex h-12 items-center justify-center rounded-xl border-2 text-sm font-bold transition-all hover:scale-[1.03]";
              const tone = isFlagged
                ? "border-amber-400 bg-amber-50 text-amber-800"
                : answered
                  ? "border-emerald-400 bg-emerald-50 text-emerald-800"
                  : "border-slate-200 bg-slate-50 text-slate-500";
              return (
                <button key={q.id} type="button" onClick={() => onJump(i)} className={`${base} ${tone}`}>
                  {i + 1}
                  {isFlagged && <Flag className="absolute -right-1.5 -top-1.5 h-3.5 w-3.5 fill-amber-400 text-amber-500" />}
                </button>
              );
            })}
          </div>

          <div className="mt-7 flex flex-wrap items-center justify-between gap-4 border-t border-slate-100 pt-5">
            <div className="flex flex-wrap items-center gap-5 text-sm font-semibold text-slate-600">
              <span className="flex items-center gap-2">
                <span className="h-4 w-4 rounded border-2 border-emerald-400 bg-emerald-50" /> Answered ({answeredCount})
              </span>
              <span className="flex items-center gap-2">
                <span className="h-4 w-4 rounded border-2 border-amber-400 bg-amber-50" /> Flagged ({flaggedCount})
              </span>
              <span className="flex items-center gap-2">
                <span className="h-4 w-4 rounded border-2 border-slate-200 bg-slate-50" /> Unanswered ({unansweredCount})
              </span>
            </div>
            <button
              type="button"
              onClick={onSubmit}
              disabled={submitting}
              className="inline-flex items-center gap-2 rounded-full bg-gradient-to-r from-blue-600 to-indigo-600 px-7 py-3 text-sm font-bold text-white shadow-md transition-opacity hover:opacity-95 disabled:opacity-60"
            >
              {submitting ? "Submitting…" : isLastModule ? "Submit Exam" : "Continue to Next Module"}
              {!submitting && <span aria-hidden>→</span>}
            </button>
          </div>
        </div>
      </main>

      <SatColorRule />
      <footer className="flex shrink-0 items-center bg-white px-6 py-3">
        {studentName ? <span className="truncate text-sm font-bold text-slate-700">{studentName}</span> : null}
      </footer>
    </div>
  );
}
