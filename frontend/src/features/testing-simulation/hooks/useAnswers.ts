"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { type Attempt, normalizeFlagged, normalizeSavedAnswers } from "../types";
import { questions as selectQuestions } from "../state/selectors";
import { readDraft } from "../services/draftStore";

export interface UseAnswersResult {
  answers: Record<string, string>;
  flagged: number[];
  eliminated: Record<string, string[]>;
  currentIndex: number;
  /** Module id the current answers belong to — used to gate autosave. */
  moduleId: number | null;

  selectAnswer: (questionId: number, value: string) => void;
  toggleFlag: (questionId: number) => void;
  toggleEliminate: (questionId: number, optionKey: string) => void;
  goTo: (index: number) => void;
  next: () => void;
  prev: () => void;
}

/**
 * Owns per-module student work (answers, flags, eliminations) and navigation.
 *
 * Rehydrates from the server snapshot (with local draft as fallback) whenever
 * the active module changes, and fully resets when the module id changes so
 * Module 1 work can never leak into Module 2.
 */
export function useAnswers(attempt: Attempt | null, attemptId: number | string): UseAnswersResult {
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [flagged, setFlagged] = useState<number[]>([]);
  const [eliminated, setEliminated] = useState<Record<string, string[]>>({});
  const [currentIndex, setCurrentIndex] = useState(0);

  const moduleId = attempt?.current_module_details?.id ?? null;
  const hydratedModuleRef = useRef<number | null>(null);

  // Rehydrate once per module id.
  useEffect(() => {
    if (moduleId == null) return;
    if (hydratedModuleRef.current === moduleId) return;
    hydratedModuleRef.current = moduleId;

    const serverAnswers = normalizeSavedAnswers(attempt?.current_module_saved_answers);
    const serverFlagged = normalizeFlagged(attempt?.current_module_flagged_questions);

    // Prefer server truth; fall back to a local draft only if the server is empty
    // (covers an offline edit that never reached the server before a refresh).
    const draft = readDraft(attemptId, moduleId);
    const hasServer = Object.keys(serverAnswers).length > 0 || serverFlagged.length > 0;

    setAnswers(hasServer ? serverAnswers : draft?.answers ?? serverAnswers);
    setFlagged(hasServer ? serverFlagged : draft?.flagged ?? serverFlagged);
    setEliminated({});
    setCurrentIndex(0);
  }, [moduleId, attempt?.current_module_saved_answers, attempt?.current_module_flagged_questions, attemptId]);

  const selectAnswer = useCallback((questionId: number, value: string) => {
    setAnswers((prev) => ({ ...prev, [questionId]: value }));
  }, []);

  const toggleFlag = useCallback((questionId: number) => {
    setFlagged((prev) => (prev.includes(questionId) ? prev.filter((id) => id !== questionId) : [...prev, questionId]));
  }, []);

  const toggleEliminate = useCallback((questionId: number, optionKey: string) => {
    // Eliminating a chosen option also deselects it.
    setAnswers((prev) => {
      if (prev[questionId] !== optionKey) return prev;
      const next = { ...prev };
      delete next[questionId];
      return next;
    });
    setEliminated((prev) => {
      const current = prev[questionId] ?? [];
      const next = current.includes(optionKey)
        ? current.filter((k) => k !== optionKey)
        : [...current, optionKey];
      return { ...prev, [questionId]: next };
    });
  }, []);

  const count = selectQuestions(attempt).length;
  const goTo = useCallback((index: number) => setCurrentIndex(() => Math.max(0, Math.min(index, Math.max(0, count - 1)))), [count]);
  const next = useCallback(() => setCurrentIndex((i) => Math.min(i + 1, Math.max(0, count - 1))), [count]);
  const prev = useCallback(() => setCurrentIndex((i) => Math.max(i - 1, 0)), []);

  return { answers, flagged, eliminated, currentIndex, moduleId, selectAnswer, toggleFlag, toggleEliminate, goTo, next, prev };
}
