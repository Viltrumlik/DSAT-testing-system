"use client";
import { useCallback, useState } from "react";
import { clamp } from "../utils/time";
import { useFullscreen } from "./useFullscreen";
import { useAnnotator, type AnnotatableContainer } from "./highlight/useAnnotator";

interface UseExamToolsArgs {
  attemptId: number | string;
  questionId: number | undefined;
  /** Live resolver for all highlightable regions (passage / question / choices). */
  getContainers: () => AnnotatableContainer[];
}

/**
 * Aggregates all SAT-experience tools into one controller so the page stays a
 * thin composition. Every member here is UI-only and isolated from the exam
 * engine (timer/autosave/submit/scoring).
 */
export function useExamTools({ attemptId, questionId, getContainers }: UseExamToolsArgs) {
  const [calculatorOpen, setCalculatorOpen] = useState(false);
  const [calculatorEnlarged, setCalculatorEnlarged] = useState(false);
  const [referenceOpen, setReferenceOpen] = useState(false);
  const [notesOpen, setNotesOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [highlighterActive, setHighlighterActive] = useState(false);
  const [zoom, setZoom] = useState(1);

  const fullscreen = useFullscreen();
  const highlighter = useAnnotator({ getContainers, attemptId, questionId, active: highlighterActive });

  const zoomIn = useCallback(() => setZoom((z) => clamp(Number((z + 0.1).toFixed(2)), 0.8, 1.6)), []);
  const zoomOut = useCallback(() => setZoom((z) => clamp(Number((z - 0.1).toFixed(2)), 0.8, 1.6)), []);

  return {
    // panels
    calculatorOpen,
    toggleCalculator: useCallback(() => {
      // Each open/close starts at the normal (non-enlarged) size.
      setCalculatorEnlarged(false);
      setCalculatorOpen((v) => !v);
    }, []),
    calculatorEnlarged,
    toggleCalculatorEnlarge: useCallback(() => setCalculatorEnlarged((v) => !v), []),
    referenceOpen,
    toggleReference: useCallback(() => setReferenceOpen((v) => !v), []),
    notesOpen,
    toggleNotes: useCallback(() => setNotesOpen((v) => !v), []),
    helpOpen,
    toggleHelp: useCallback(() => setHelpOpen((v) => !v), []),
    closeHelp: useCallback(() => setHelpOpen(false), []),
    // highlighter
    highlighterActive,
    toggleHighlighter: useCallback(() => setHighlighterActive((v) => !v), []),
    highlighter,
    // zoom
    zoom,
    zoomIn,
    zoomOut,
    // fullscreen
    fullscreen,
  };
}

export type ExamTools = ReturnType<typeof useExamTools>;
