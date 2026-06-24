"use client";
import { Flag, MapPin, X } from "lucide-react";
import type { ExamQuestion } from "../types";

interface QuestionNavigatorProps {
  open: boolean;
  onClose: () => void;
  title: string;
  questions: ExamQuestion[];
  currentIndex: number;
  answers: Record<string, string>;
  flagged: number[];
  onJump: (index: number) => void;
  /** Opens the Check Your Work review page. */
  onGoToReview: () => void;
}

/**
 * Question-jump grid (current / unanswered / for-review). Opens as a popover
 * anchored to the bottom, just above the footer's "Question X of Y" button, with
 * a downward pointer to it (Bluebook-style) rather than a centered modal.
 */
export function QuestionNavigator({
  open,
  onClose,
  title,
  questions,
  currentIndex,
  answers,
  flagged,
  onJump,
  onGoToReview,
}: QuestionNavigatorProps) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-40 flex items-end justify-center bg-black/20 pb-[68px]" onClick={onClose}>
      <div className="relative mx-4 w-full max-w-lg rounded-2xl bg-white p-6 shadow-2xl" onClick={(e) => e.stopPropagation()}>
        {/* Downward pointer to the "Question X of Y" button below. */}
        <div className="absolute left-1/2 top-full h-0 w-0 -translate-x-1/2 border-x-8 border-t-8 border-x-transparent border-t-white" />
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-bold tracking-tight text-slate-900">{title}</h3>
          <button type="button" onClick={onClose} className="text-slate-400 hover:text-slate-700">
            <X className="h-5 w-5" />
          </button>
        </div>
        <div className="mb-5 flex items-center justify-center gap-6 border-b border-slate-100 pb-3 text-sm font-semibold text-slate-600">
          <span className="flex items-center gap-1.5"><MapPin className="h-4 w-4 fill-slate-800 text-slate-800" /> Current</span>
          <span className="flex items-center gap-1.5"><span className="h-3.5 w-3.5 rounded-sm border border-dashed border-slate-400" /> Unanswered</span>
          <span className="flex items-center gap-1.5"><Flag className="h-4 w-4 fill-red-500 text-red-500" /> For Review</span>
        </div>
        <div className="grid grid-cols-6 gap-x-3 gap-y-2 pt-3">
          {questions.map((q, i) => {
            const answered = Boolean(answers[q.id]);
            const isCurrent = i === currentIndex;
            const isFlagged = flagged.includes(q.id);
            return (
              <div key={q.id} className="relative flex justify-center">
                {isCurrent && <MapPin className="absolute -top-3 left-1/2 h-4 w-4 -translate-x-1/2 fill-slate-800 text-slate-800" aria-hidden />}
                <button
                  type="button"
                  onClick={() => {
                    onJump(i);
                    onClose();
                  }}
                  aria-current={isCurrent ? "true" : undefined}
                  className={`relative flex h-10 w-10 items-center justify-center rounded-md text-sm font-bold transition-colors ${
                    answered
                      ? "border border-slate-800 bg-slate-800 text-white"
                      : "border border-dashed border-slate-400 text-slate-700 hover:border-slate-600"
                  } ${isCurrent ? "underline underline-offset-2" : ""}`}
                >
                  {i + 1}
                  {isFlagged && <Flag className="absolute -right-1.5 -top-1.5 h-3.5 w-3.5 fill-red-500 text-red-500" aria-hidden />}
                </button>
              </div>
            );
          })}
        </div>
        <div className="mt-5 flex justify-center border-t border-slate-100 pt-4">
          <button
            type="button"
            onClick={() => {
              onClose();
              onGoToReview();
            }}
            className="rounded-full border-2 border-blue-600 px-6 py-2 text-sm font-bold text-blue-700 transition-colors hover:bg-blue-50"
          >
            Go to Review Page
          </button>
        </div>
      </div>
    </div>
  );
}
