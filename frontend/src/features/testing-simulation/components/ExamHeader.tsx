"use client";
import { Calculator, ChevronDown, Highlighter, StickyNote } from "lucide-react";
import { Timer } from "./Timer";
import { MoreMenu } from "../tools/MoreMenu";
import type { ExamTools } from "../tools/useExamTools";

interface ExamHeaderProps {
  moduleTitle: string;
  secondsLeft: number;
  timerHidden: boolean;
  onToggleTimer: () => void;
  timerWarning: boolean;
  showDirections: boolean;
  onToggleDirections: () => void;
  /** Reference sheet is SAT Math-only. */
  mathTools: boolean;
  /** Calculator: Math-only AND not a midterm (midterms have no calculator). */
  showCalculator: boolean;
  tools: ExamTools;
  pauseAllowed: boolean;
  paused: boolean;
  onTogglePause: () => void;
  onSaveAndExit: () => void;
}

function ToolButton({ label, active, onClick, children }: { label: string; active?: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`flex flex-col items-center text-xs font-semibold ${active ? "text-blue-700" : "text-slate-600 hover:text-slate-900"}`}
    >
      {children}
      {label}
    </button>
  );
}

/** Top bar: title/Directions, central timer, and the SAT tool cluster. */
export function ExamHeader({
  moduleTitle,
  secondsLeft,
  timerHidden,
  onToggleTimer,
  timerWarning,
  showDirections,
  onToggleDirections,
  mathTools,
  showCalculator,
  tools,
  pauseAllowed,
  paused,
  onTogglePause,
  onSaveAndExit,
}: ExamHeaderProps) {
  return (
    <header className="grid shrink-0 grid-cols-3 items-center bg-white px-6 py-3">
      <div className="flex flex-col items-start">
        <h1 className="text-base font-bold tracking-tight text-slate-900">{moduleTitle}</h1>
        <button
          type="button"
          onClick={onToggleDirections}
          aria-expanded={showDirections}
          className="mt-0.5 inline-flex items-center gap-1 text-sm font-semibold text-slate-700 hover:text-slate-900"
        >
          Directions <ChevronDown className="h-4 w-4" />
        </button>
      </div>

      <div className="flex justify-center">
        {/* Pause sits beside Hide as a matching pill (item: Pause Button). */}
        <Timer
          secondsLeft={secondsLeft}
          hidden={timerHidden}
          onToggleHidden={onToggleTimer}
          warning={timerWarning}
          pauseAllowed={pauseAllowed}
          paused={paused}
          onTogglePause={onTogglePause}
        />
      </div>

      <div className="flex items-center justify-end gap-5">
        {showCalculator && (
          <ToolButton label="Calculator" active={tools.calculatorOpen} onClick={tools.toggleCalculator}>
            <Calculator className="h-5 w-5" />
          </ToolButton>
        )}
        {mathTools && (
          <ToolButton label="Reference" active={tools.referenceOpen} onClick={tools.toggleReference}>
            <span className="text-base font-bold italic leading-none">x²</span>
          </ToolButton>
        )}
        <ToolButton label="Highlights" active={tools.highlighterActive} onClick={tools.toggleHighlighter}>
          <Highlighter className="h-5 w-5" />
        </ToolButton>
        <ToolButton label="Notes" active={tools.notesOpen} onClick={tools.toggleNotes}>
          <StickyNote className="h-5 w-5" />
        </ToolButton>
        <MoreMenu
          isFullscreen={tools.fullscreen.isFullscreen}
          onToggleFullscreen={tools.fullscreen.toggle}
          highlighterActive={tools.highlighterActive}
          onToggleHighlighter={tools.toggleHighlighter}
          onZoomIn={tools.zoomIn}
          onZoomOut={tools.zoomOut}
          onToggleHelp={tools.toggleHelp}
          pauseAllowed={pauseAllowed}
          paused={paused}
          onTogglePause={onTogglePause}
          onSaveAndExit={onSaveAndExit}
        />
      </div>
    </header>
  );
}
