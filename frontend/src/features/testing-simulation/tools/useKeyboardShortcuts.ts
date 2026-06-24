"use client";
import { useEffect, useRef } from "react";

export interface ShortcutHandlers {
  onPrev: () => void;
  onNext: () => void;
  /** Select an answer choice by zero-based index (0=A … 3=D). */
  onSelectChoice: (index: number) => void;
  onToggleMark: () => void;
  onToggleNavigator: () => void;
  onToggleHelp: () => void;
  enabled: boolean;
}

function isTypingTarget(el: EventTarget | null): boolean {
  const node = el as HTMLElement | null;
  if (!node) return false;
  const tag = node.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || node.isContentEditable;
}

/**
 * Global keyboard shortcuts for the runner. Pure input handling — it only calls
 * the navigation/marking callbacks it's given; it never reads or mutates engine
 * state. Disabled while typing in inputs (e.g. SPR, Notes).
 */
export function useKeyboardShortcuts(handlers: ShortcutHandlers) {
  const ref = useRef(handlers);
  useEffect(() => {
    ref.current = handlers;
  });

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const h = ref.current;
      if (!h.enabled || e.metaKey || e.ctrlKey || e.altKey) return;
      if (isTypingTarget(e.target)) return;

      switch (e.key) {
        case "ArrowLeft": h.onPrev(); break;
        case "ArrowRight": h.onNext(); break;
        case "a": case "A": h.onSelectChoice(0); break;
        case "b": case "B": h.onSelectChoice(1); break;
        case "c": case "C": h.onSelectChoice(2); break;
        case "d": case "D": h.onSelectChoice(3); break;
        case "m": case "M": h.onToggleMark(); break;
        case "r": case "R": h.onToggleNavigator(); break;
        case "?": h.onToggleHelp(); break;
        default: return;
      }
      e.preventDefault();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
}

export const SHORTCUTS: Array<{ keys: string; action: string }> = [
  { keys: "← / →", action: "Previous / Next question" },
  { keys: "A B C D", action: "Select answer choice" },
  { keys: "M", action: "Mark for review" },
  { keys: "R", action: "Open question navigator" },
  { keys: "?", action: "Show this help" },
];
