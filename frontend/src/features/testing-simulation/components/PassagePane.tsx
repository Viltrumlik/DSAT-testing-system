"use client";
import { memo } from "react";
import SafeHtml from "@/components/SafeHtml";
import type { ExamQuestion } from "../types";
import { resolveImageUrl } from "../utils/image";
import { renderExamHtml } from "../utils/richContent";

interface PassagePaneProps {
  question: ExamQuestion;
  zoom: number;
  style?: React.CSSProperties;
}

/** Left pane: the stimulus/passage and any figure. Read-only. */
export const PassagePane = memo(function PassagePane({ question, zoom, style }: PassagePaneProps) {
  const figure = resolveImageUrl(question.question_image);
  return (
    <div
      className="min-w-0 overflow-y-auto border-r border-slate-200 p-10"
      style={{ fontSize: `${16 * zoom}px`, ...style }}
    >
      <div id="ts-passage" className="prose prose-slate max-w-none font-sans leading-relaxed text-slate-800">
        {figure && (
          <div className="mb-6 flex justify-center rounded-lg border border-slate-100 bg-slate-50 p-4">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={figure} alt="Passage figure" className="max-h-[400px] max-w-full object-contain" />
          </div>
        )}
        <SafeHtml
          className="mathjax-process font-[Georgia] font-medium leading-relaxed"
          html={renderExamHtml(question.question_text)}
        />
      </div>
    </div>
  );
});
