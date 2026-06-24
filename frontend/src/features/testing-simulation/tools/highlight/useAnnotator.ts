"use client";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import {
  addHighlight,
  addUnderline,
  annotationsAt,
  applyAnnotations,
  boundingRange,
  clearAnnotations,
  type Annotation,
  type HighlightColor,
  markFromEvent,
  offsetsOfMark,
  type OffsetRange,
  rangeToOffsets,
  removeRange,
  type UnderlineStyle,
} from "./annotations";
import { readAnnotations, writeAnnotations } from "./annotationStore";

/** A highlightable region with a stable key + its own offset space. */
export interface AnnotatableContainer {
  key: string;
  el: HTMLElement | null;
}

interface UseAnnotatorArgs {
  /** Live resolver for all annotatable regions (passage / question / choices). */
  getContainers: () => AnnotatableContainer[];
  attemptId: number | string;
  questionId: number | undefined;
  active: boolean;
}

export interface AnnotatorToolbar {
  x: number;
  top: number;
  bottom: number;
  /** Which container the range lives in. */
  container: string;
  range: OffsetRange;
  current: { color?: HighlightColor; underline?: UnderlineStyle };
}

const DEFAULT_COLOR: HighlightColor = "yellow";

/** Styles covering the entire range (drives the active toolbar buttons). */
function stylesOver(anns: Annotation[], range: OffsetRange) {
  const color = anns.find((a) => a.kind === "highlight" && a.start <= range.start && a.end >= range.end)?.color;
  const underline = anns.find((a) => a.kind === "underline" && a.start <= range.start && a.end >= range.end)?.underline;
  return { color, underline };
}

/**
 * Bluebook-style text annotator across multiple regions (passage, question
 * prompt/stem, answer choices). Selecting text immediately highlights it in the
 * active colour (default yellow) and opens a toolbar to recolour, underline or
 * delete. Clicking an existing annotation re-opens the toolbar to edit it.
 *
 * Each region has its own character-offset space and localStorage entry, so
 * annotations on the passage, prompt and choices are independent. Marks are
 * repainted after every commit (the regions render via dangerouslySetInnerHTML,
 * which React resets on re-render) — restored before the browser paints.
 */
export function useAnnotator({ getContainers, attemptId, questionId, active }: UseAnnotatorArgs) {
  const [toolbar, setToolbar] = useState<AnnotatorToolbar | null>(null);
  const [activeColor, setActiveColor] = useState<HighlightColor>(DEFAULT_COLOR);

  const containersRef = useRef(getContainers);
  const activeColorRef = useRef(activeColor);
  useEffect(() => {
    containersRef.current = getContainers;
    activeColorRef.current = activeColor;
  });

  const containers = useCallback(() => containersRef.current().filter((c) => c.el), []);
  const elFor = useCallback((k: string) => containersRef.current().find((c) => c.key === k)?.el ?? null, []);

  // Paint every region from its stored annotations, skipping a region the user
  // is actively selecting in (so a drag isn't disrupted).
  const paint = useCallback(() => {
    if (questionId == null) return;
    const sel = window.getSelection();
    const activeNode = sel && !sel.isCollapsed ? sel.anchorNode : null;
    for (const { key, el } of containers()) {
      if (!el) continue;
      if (activeNode && el.contains(activeNode)) continue;
      applyAnnotations(el, readAnnotations(attemptId, questionId, key));
    }
  }, [containers, attemptId, questionId]);

  // Drop the toolbar on question change; repaint once after KaTeX settles.
  useEffect(() => {
    setToolbar(null);
    const t = setTimeout(paint, 150);
    return () => clearTimeout(t);
  }, [questionId, attemptId, paint]);

  // Re-apply after EVERY commit — the regions render via dangerouslySetInnerHTML,
  // so routine re-renders (timer, toolbar, navigation) reset their HTML and would
  // otherwise wipe the marks. Layout effect → restored before the browser paints.
  useLayoutEffect(() => {
    paint();
  });

  useEffect(() => {
    if (!active || questionId == null) return;

    const onMouseUp = (e: MouseEvent) => {
      if ((e.target as HTMLElement | null)?.closest?.("[data-annot-toolbar]")) return;
      const list = containers();
      const sel = window.getSelection();

      // New selection inside a single region → auto-apply the active colour.
      if (sel && !sel.isCollapsed && sel.rangeCount > 0) {
        const c = list.find((c) => c.el!.contains(sel.anchorNode) && c.el!.contains(sel.focusNode));
        if (c && c.el) {
          const range = sel.getRangeAt(0);
          const off = rangeToOffsets(c.el, range);
          if (off) {
            const color = activeColorRef.current;
            const next = addHighlight(readAnnotations(attemptId, questionId, c.key), off, color);
            applyAnnotations(c.el, writeAnnotations(attemptId, questionId, c.key, next));
            const rect = range.getBoundingClientRect();
            setToolbar({
              x: rect.left + rect.width / 2,
              top: rect.top,
              bottom: rect.bottom,
              container: c.key,
              range: off,
              current: { color },
            });
            sel.removeAllRanges();
          }
        }
        return;
      }

      // Click on an existing annotation → open the toolbar to edit it.
      const mark = markFromEvent(e.target);
      if (mark) {
        const c = list.find((c) => c.el!.contains(mark));
        if (c && c.el) {
          const markRange = offsetsOfMark(c.el, mark);
          if (markRange) {
            const anns = readAnnotations(attemptId, questionId, c.key);
            const range = boundingRange(annotationsAt(anns, markRange.start)) ?? markRange;
            setToolbar({ x: e.clientX, top: e.clientY, bottom: e.clientY, container: c.key, range, current: stylesOver(anns, range) });
          }
        }
        return;
      }

      setToolbar(null);
    };

    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setToolbar(null);
    };

    document.addEventListener("mouseup", onMouseUp);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mouseup", onMouseUp);
      document.removeEventListener("keydown", onKey);
    };
  }, [active, questionId, attemptId, containers]);

  const commit = useCallback(
    (container: string, next: Annotation[]) => {
      if (questionId == null) return;
      const el = elFor(container);
      const saved = writeAnnotations(attemptId, questionId, container, next);
      if (el) applyAnnotations(el, saved);
      window.getSelection()?.removeAllRanges();
    },
    [elFor, attemptId, questionId],
  );

  const applyColor = useCallback(
    (color: HighlightColor) => {
      setActiveColor(color);
      if (!toolbar || questionId == null) return;
      commit(toolbar.container, addHighlight(readAnnotations(attemptId, questionId, toolbar.container), toolbar.range, color));
      setToolbar((t) => (t ? { ...t, current: { ...t.current, color } } : t));
    },
    [toolbar, attemptId, questionId, commit],
  );

  const applyUnderline = useCallback(
    (underline: UnderlineStyle) => {
      if (!toolbar || questionId == null) return;
      commit(toolbar.container, addUnderline(readAnnotations(attemptId, questionId, toolbar.container), toolbar.range, underline));
      setToolbar((t) => (t ? { ...t, current: { ...t.current, underline } } : t));
    },
    [toolbar, attemptId, questionId, commit],
  );

  const deleteAnnotation = useCallback(() => {
    if (!toolbar || questionId == null) {
      setToolbar(null);
      return;
    }
    commit(toolbar.container, removeRange(readAnnotations(attemptId, questionId, toolbar.container), toolbar.range));
    setToolbar(null);
  }, [toolbar, attemptId, questionId, commit]);

  const clearAll = useCallback(() => {
    if (questionId == null) return;
    for (const { key, el } of containers()) {
      if (el) clearAnnotations(el);
      writeAnnotations(attemptId, questionId, key, []);
    }
    setToolbar(null);
  }, [containers, attemptId, questionId]);

  return { toolbar, applyColor, applyUnderline, deleteAnnotation, dismiss: () => setToolbar(null), clearAll };
}
