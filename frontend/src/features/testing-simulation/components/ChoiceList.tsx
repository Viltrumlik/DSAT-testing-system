"use client";
import SafeHtml from "@/components/SafeHtml";
import type { ExamQuestion } from "../types";
import { parseOptions } from "../utils/options";
import { resolveImageUrl } from "../utils/image";
import { renderExamHtml } from "../utils/richContent";

interface ChoiceListProps {
  question: ExamQuestion;
  selected: string | undefined;
  eliminated: string[];
  eliminationMode: boolean;
  onSelect: (key: string) => void;
  onEliminate: (key: string) => void;
}

/** Multiple-choice answer list with select + cross-out (eliminate) support. */
export function ChoiceList({ question, selected, eliminated, eliminationMode, onSelect, onEliminate }: ChoiceListProps) {
  const options = parseOptions(question);
  return (
    <div className="w-full space-y-4">
      {options.map(({ key, text, image }) => {
        const isSelected = selected === key;
        const isEliminated = eliminated.includes(key);
        const img = resolveImageUrl(image);
        return (
          <div key={key} className="group relative flex items-center gap-3">
            <button
              type="button"
              onClick={() => !isEliminated && onSelect(key)}
              aria-pressed={isSelected}
              className={`flex min-h-[50px] flex-1 items-center rounded-xl border-2 p-3 px-4 transition-all ${
                isSelected
                  ? "border-blue-600 bg-blue-50/20 outline outline-2 outline-offset-1 outline-blue-600"
                  : isEliminated
                    ? "cursor-not-allowed border-slate-100 opacity-50 grayscale"
                    : "border-slate-300 bg-white hover:border-slate-400"
              }`}
            >
              <span
                className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full border-2 font-[Georgia] text-sm font-bold ${
                  isSelected
                    ? "border-blue-600 bg-blue-600 text-white"
                    : isEliminated
                      ? "border-slate-300 text-slate-400"
                      : "border-slate-400 text-slate-800"
                }`}
              >
                {key}
              </span>
              <span className={`ml-4 w-full text-left font-[Georgia] text-[15px] text-slate-800 ${isEliminated ? "line-through decoration-slate-400" : ""}`}>
                {img ? (
                  /* eslint-disable-next-line @next/next/no-img-element */
                  <img src={img} alt={`Option ${key}`} className="max-h-[200px] max-w-full rounded-lg border border-slate-100 object-contain shadow-sm" />
                ) : (
                  <SafeHtml className="mathjax-process w-full" html={renderExamHtml(text)} />
                )}
              </span>
            </button>

            {eliminationMode &&
              (isEliminated ? (
                // Eliminated → an "Undo" pill (Bluebook restores via a text link).
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    onEliminate(key);
                  }}
                  title="Restore"
                  className="shrink-0 text-xs font-bold text-blue-700 underline underline-offset-2 hover:text-blue-800"
                >
                  Undo
                </button>
              ) : (
                // Crossed-out circular letter (Bluebook eliminate control).
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    onEliminate(key);
                  }}
                  title={`Eliminate ${key}`}
                  aria-label={`Eliminate ${key}`}
                  className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-slate-400 text-slate-600 transition-colors hover:border-slate-600 hover:text-slate-900"
                >
                  <span className="relative text-xs font-bold leading-none">
                    {key}
                    <span className="absolute left-1/2 top-1/2 h-px w-5 -translate-x-1/2 -translate-y-1/2 bg-current" />
                  </span>
                </button>
              ))}
          </div>
        );
      })}
    </div>
  );
}
