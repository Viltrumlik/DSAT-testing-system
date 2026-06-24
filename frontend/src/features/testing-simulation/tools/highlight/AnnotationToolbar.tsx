"use client";
import { useLayoutEffect, useRef, useState } from "react";
import { Trash2, Underline, X } from "lucide-react";
import type { HighlightColor, UnderlineStyle } from "./annotations";
import type { AnnotatorToolbar } from "./useAnnotator";

interface AnnotationToolbarProps {
  toolbar: AnnotatorToolbar;
  onColor: (color: HighlightColor) => void;
  onUnderline: (style: UnderlineStyle) => void;
  onDelete: () => void;
  onClose: () => void;
}

const SWATCHES: Array<{ color: HighlightColor; bg: string; label: string }> = [
  { color: "yellow", bg: "#fde047", label: "Yellow highlight" },
  { color: "blue", bg: "#93c5fd", label: "Blue highlight" },
  { color: "pink", bg: "#f9a8d4", label: "Pink highlight" },
];

const LINES: Array<{ style: UnderlineStyle; css: string; label: string }> = [
  { style: "solid", css: "border-solid", label: "Solid underline" },
  { style: "dashed", css: "border-dashed", label: "Dashed underline" },
  { style: "dotted", css: "border-dotted", label: "Dotted underline" },
];

const ICON_BTN = "flex h-7 w-7 items-center justify-center rounded-md text-slate-600 hover:bg-slate-100";
const DIVIDER = "mx-1 h-6 w-px bg-slate-200";

/**
 * Bluebook-style annotation toolbar.
 *   Top row:    yellow · blue · pink | underline | delete
 *   Bottom row: solid · dashed · dotted | close
 *
 * Positions itself just above the selection, clamped to stay fully on-screen
 * (flips below the selection when there isn't room above). Tagged
 * `data-annot-toolbar` so the annotator's document mouseup ignores clicks here.
 */
export function AnnotationToolbar({ toolbar, onColor, onUnderline, onDelete, onClose }: AnnotationToolbarProps) {
  const ref = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<{ left: number; top: number } | null>(null);
  const { color: activeColor, underline: activeUnderline } = toolbar.current;

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const w = el.offsetWidth;
    const h = el.offsetHeight;
    const margin = 8;
    let left = toolbar.x - w / 2;
    left = Math.max(margin, Math.min(left, window.innerWidth - w - margin));
    let top = toolbar.top - h - 10; // prefer above the selection
    if (top < margin) top = toolbar.bottom + 10; // not enough room → below
    top = Math.max(margin, Math.min(top, window.innerHeight - h - margin));
    setPos({ left, top });
  }, [toolbar.x, toolbar.top, toolbar.bottom]);

  return (
    <div
      ref={ref}
      data-annot-toolbar
      role="toolbar"
      aria-label="Annotation options"
      className="fixed z-[70] flex flex-col gap-1 rounded-xl border border-slate-200 bg-white px-1.5 py-1.5 shadow-xl"
      style={{ left: pos?.left ?? -9999, top: pos?.top ?? -9999, visibility: pos ? "visible" : "hidden" }}
    >
      {/* Top row: colours · underline · delete */}
      <div className="flex items-center gap-1">
        {SWATCHES.map((s) => (
          <button
            key={s.color}
            type="button"
            title={s.label}
            aria-label={s.label}
            aria-pressed={activeColor === s.color}
            onClick={() => onColor(s.color)}
            className={`h-7 w-7 rounded-md transition-transform hover:scale-110 ${
              activeColor === s.color ? "ring-2 ring-slate-900 ring-offset-1" : "ring-1 ring-slate-200"
            }`}
            style={{ backgroundColor: s.bg }}
          />
        ))}
        <span className={DIVIDER} />
        <button
          type="button"
          title="Underline"
          aria-label="Underline"
          aria-pressed={Boolean(activeUnderline)}
          onClick={() => onUnderline(activeUnderline ?? "solid")}
          className={`${ICON_BTN} ${activeUnderline ? "bg-blue-50 text-blue-700" : ""}`}
        >
          <Underline className="h-4 w-4" />
        </button>
        <button type="button" title="Delete" aria-label="Delete annotation" onClick={onDelete} className={`${ICON_BTN} hover:bg-red-50 hover:text-red-600`}>
          <Trash2 className="h-4 w-4" />
        </button>
      </div>

      {/* Bottom row: underline styles · close */}
      <div className="flex items-center gap-1 border-t border-slate-100 pt-1">
        {LINES.map((l) => (
          <button
            key={l.style}
            type="button"
            title={l.label}
            aria-label={l.label}
            aria-pressed={activeUnderline === l.style}
            onClick={() => onUnderline(l.style)}
            className={`${ICON_BTN} ${activeUnderline === l.style ? "bg-blue-50" : ""}`}
          >
            <span className={`block w-4 border-b-2 ${l.css} border-slate-700`} />
          </button>
        ))}
        <span className={DIVIDER} />
        <button type="button" title="Close" aria-label="Close" onClick={onClose} className={ICON_BTN}>
          <X className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
