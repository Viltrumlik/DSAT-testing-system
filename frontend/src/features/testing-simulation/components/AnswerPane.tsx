"use client";
import { memo } from "react";
import { Bookmark } from "lucide-react";
import SafeHtml from "@/components/SafeHtml";
import type { ExamQuestion } from "../types";
import { ChoiceList } from "./ChoiceList";
import { SprInput } from "./SprInput";
import { renderExamHtml } from "../utils/richContent";
import { resolveImageUrl } from "../utils/image";

interface AnswerPaneProps {
  question: ExamQuestion;
  displayNumber: number;
  zoom: number;
  isMath: boolean;
  flagged: boolean;
  onToggleFlag: () => void;
  eliminationMode: boolean;
  onToggleEliminationMode: () => void;
  answer: string | undefined;
  eliminated: string[];
  onSelect: (key: string) => void;
  onEliminate: (key: string) => void;
  style?: React.CSSProperties;
  /** Left space (px) to reserve when the calculator is open, so the floating
   *  Desmos window never covers the question content. 0 = no calculator. */
  calcReserve?: number;
}

/** Right pane: question header (number, Mark for Review, eliminate toggle) + answer area. */
export const AnswerPane = memo(function AnswerPane({
  question,
  displayNumber,
  zoom,
  isMath,
  flagged,
  onToggleFlag,
  eliminationMode,
  onToggleEliminationMode,
  answer,
  eliminated,
  onSelect,
  onEliminate,
  style,
  calcReserve = 0,
}: AnswerPaneProps) {
  const isSpr = Boolean(question.is_math_input);
  // Math is single-pane (no PassagePane), so the question figure is rendered here.
  const figure = isMath ? resolveImageUrl(question.question_image) : undefined;
  return (
    <div
      className="min-w-0 overflow-y-auto overflow-x-hidden bg-white p-10 pb-8 transition-[padding] duration-300 ease-out"
      style={{ fontSize: `${15 * zoom}px`, ...(calcReserve > 0 ? { paddingLeft: calcReserve } : null), ...style }}
    >
      <div className={`w-full max-w-3xl ${calcReserve > 0 ? "mr-auto" : "mx-auto"}`}>
        {/* Question header band — coloured block, kept within the centred content. */}
        <div className="mb-4 flex items-center justify-between rounded-lg bg-stone-100 px-4 py-2.5">
          <div className="flex items-center gap-6">
            <span className="flex items-center justify-center rounded-md bg-slate-900 px-3 py-1.5 text-sm font-bold tracking-tight text-white">
              {displayNumber}
            </span>
            <button
              type="button"
              onClick={onToggleFlag}
              className={`flex items-center text-xs font-bold underline-offset-2 transition-colors ${flagged ? "text-red-600 underline" : "text-slate-500 hover:text-slate-900"}`}
            >
              <span className={`mr-1.5 flex h-5 w-5 items-center justify-center rounded-sm border ${flagged ? "border-red-300" : "border-slate-400"}`}>
                <Bookmark className={`h-3.5 w-3.5 ${flagged ? "fill-red-600 text-red-600" : "text-slate-400"}`} />
              </span>
              {flagged ? "Marked for Review" : "Mark for Review"}
            </button>
          </div>
          {/* Answer-elimination toggle is meaningless for SPR (no choices). */}
          {!isSpr && (
            <button
              type="button"
              onClick={onToggleEliminationMode}
              title="Eliminate answer choices"
              className={`flex items-center justify-center rounded-md border-2 p-1 px-1.5 transition-all ${eliminationMode ? "border-blue-600 bg-blue-50 text-blue-700" : "border-slate-300 text-slate-600 hover:border-slate-400"}`}
            >
              <span className="relative">
                <span className="text-[10px] font-black italic tracking-tighter">ABC</span>
                <span className="absolute left-1/2 top-1/2 h-[1.5px] w-full -translate-x-1/2 -translate-y-1/2 rotate-[15deg] bg-current" />
              </span>
            </button>
          )}
        </div>

        {/* Decorative SAT rule */}
        <div
          className="mb-8 h-[3px] w-full"
          style={{
            background:
              "repeating-linear-gradient(to right, #b91c1c 0, #b91c1c 48px, transparent 48px, transparent 54px, #ca8a04 54px, #ca8a04 102px, transparent 102px, transparent 108px, #15803d 108px, #15803d 156px, transparent 156px, transparent 162px, #0f172a 162px, #0f172a 210px, transparent 210px, transparent 216px)",
          }}
        />
        {/* Math question figure (single-pane layout has no PassagePane). */}
        {figure && (
          <div className="mb-6 flex justify-center">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={figure}
              alt="Question figure"
              className="max-h-[360px] max-w-full rounded-lg border border-slate-100 bg-slate-50 object-contain p-2"
            />
          </div>
        )}

        {/* Highlightable question content (prompt for RW, stem for math). The
            annotator targets this container when there is no passage pane. */}
        <div id="ts-question">
          {question.question_prompt && !isSpr && (
            <SafeHtml
              className="mathjax-process mb-8 font-[Georgia] font-medium leading-relaxed text-slate-900"
              style={{ fontSize: `${16 * zoom * 1.2}px` }}
              html={renderExamHtml(question.question_prompt)}
            />
          )}
          {isMath && (
            <SafeHtml
              className="mathjax-process mb-8 font-[Georgia] font-medium leading-relaxed text-slate-900"
              style={{ fontSize: `${16 * zoom * 1.2}px` }}
              html={renderExamHtml(question.question_text)}
            />
          )}
        </div>

        {isSpr ? (
          <SprInput value={answer ?? ""} onChange={onSelect} />
        ) : (
          <div id="ts-choices">
            <ChoiceList
              question={question}
              selected={answer}
              eliminated={eliminated}
              eliminationMode={eliminationMode}
              onSelect={onSelect}
              onEliminate={onEliminate}
            />
          </div>
        )}
      </div>
    </div>
  );
});
