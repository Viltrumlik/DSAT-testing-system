"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { X } from "lucide-react";

interface FloatingPanelProps {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
  initial?: { x: number; y: number; w: number; h: number };
  minW?: number;
  minH?: number;
  resizable?: boolean;
  /** Extra controls rendered in the title bar, left of the close button. */
  headerExtra?: React.ReactNode;
  /** Replaces the title text on the left of the bar (e.g. tabs). */
  headerLeft?: React.ReactNode;
  /** Dark (navy) title bar. */
  dark?: boolean;
}

/**
 * Shared draggable + (optionally) resizable floating window. Pure UI — holds no
 * exam state and never imports an engine hook. Used by Calculator, Reference,
 * Notes. Drag by the title bar; resize from the bottom-right grip.
 */
export function FloatingPanel({
  title,
  onClose,
  children,
  initial = { x: 120, y: 90, w: 380, h: 520 },
  minW = 280,
  minH = 200,
  resizable = true,
  headerExtra,
  headerLeft,
  dark = false,
}: FloatingPanelProps) {
  const [pos, setPos] = useState({ x: initial.x, y: initial.y });
  const [size, setSize] = useState({ w: initial.w, h: initial.h });
  const drag = useRef<{ mode: "move" | "resize"; dx: number; dy: number } | null>(null);

  // Resize when the caller changes the requested size (e.g. enlarge toggle).
  useEffect(() => {
    setSize({ w: initial.w, h: initial.h });
  }, [initial.w, initial.h]);

  const onHeaderDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      drag.current = { mode: "move", dx: e.clientX - pos.x, dy: e.clientY - pos.y };
    },
    [pos.x, pos.y],
  );
  const onGripDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      e.stopPropagation();
      drag.current = { mode: "resize", dx: e.clientX - size.w, dy: e.clientY - size.h };
    },
    [size.w, size.h],
  );

  useEffect(() => {
    const move = (e: MouseEvent) => {
      const d = drag.current;
      if (!d) return;
      if (d.mode === "move") {
        const maxX = window.innerWidth - 120;
        const maxY = window.innerHeight - 60;
        setPos({ x: Math.min(maxX, Math.max(0, e.clientX - d.dx)), y: Math.min(maxY, Math.max(0, e.clientY - d.dy)) });
      } else {
        setSize({ w: Math.max(minW, e.clientX - d.dx), h: Math.max(minH, e.clientY - d.dy) });
      }
    };
    const up = () => (drag.current = null);
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
    return () => {
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", up);
    };
  }, [minW, minH]);

  return (
    <div
      className="fixed z-50 flex flex-col overflow-hidden rounded-xl border border-slate-300 bg-white shadow-2xl"
      style={{ left: pos.x, top: pos.y, width: size.w, height: size.h }}
      role="dialog"
      aria-label={title}
    >
      <div
        onMouseDown={onHeaderDown}
        className={`flex shrink-0 cursor-move items-center justify-between border-b px-3 py-2 select-none ${
          dark ? "border-slate-700 bg-slate-900" : "border-slate-200 bg-slate-50"
        }`}
      >
        {headerLeft ?? <span className={`text-sm font-bold ${dark ? "text-white" : "text-slate-700"}`}>{title}</span>}
        <div className="flex items-center gap-1">
          {headerExtra}
          <button
            type="button"
            onClick={onClose}
            className={`rounded p-0.5 ${dark ? "text-slate-300 hover:bg-white/10 hover:text-white" : "text-slate-400 hover:bg-slate-200 hover:text-slate-700"}`}
            aria-label={`Close ${title}`}
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-auto">{children}</div>
      {resizable && (
        <div
          onMouseDown={onGripDown}
          className="absolute bottom-0 right-0 h-4 w-4 cursor-se-resize"
          style={{ background: "linear-gradient(135deg, transparent 50%, #94a3b8 50%)" }}
          aria-hidden
        />
      )}
    </div>
  );
}
