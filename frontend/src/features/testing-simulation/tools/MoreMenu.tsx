"use client";
import { useEffect, useRef, useState } from "react";
import { Highlighter, Keyboard, LogOut, Maximize, Minimize, MoreVertical, Pause, Play, ZoomIn, ZoomOut } from "lucide-react";

export interface MoreMenuProps {
  isFullscreen: boolean;
  onToggleFullscreen: () => void;
  highlighterActive: boolean;
  onToggleHighlighter: () => void;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onToggleHelp: () => void;
  pauseAllowed: boolean;
  paused: boolean;
  onTogglePause: () => void;
  onSaveAndExit: () => void;
}

/** "More" dropdown housing the secondary SAT tools. Each item is a plain callback. */
export function MoreMenu(props: MoreMenuProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  const item = (icon: React.ReactNode, label: string, onClick: () => void, active = false) => (
    <button
      type="button"
      onClick={() => {
        onClick();
        setOpen(false);
      }}
      className={`flex w-full items-center gap-3 px-4 py-2 text-left text-sm font-semibold hover:bg-slate-50 ${active ? "text-blue-700" : "text-slate-700"}`}
    >
      {icon}
      {label}
    </button>
  );

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        className="flex flex-col items-center text-xs font-semibold text-slate-600 hover:text-slate-900"
      >
        <MoreVertical className="h-5 w-5" />
        More
      </button>
      {open && (
        <div role="menu" className="absolute right-0 top-full z-50 mt-2 w-60 overflow-hidden rounded-xl border border-slate-200 bg-white py-1 shadow-xl">
          {item(props.isFullscreen ? <Minimize className="h-4 w-4" /> : <Maximize className="h-4 w-4" />, props.isFullscreen ? "Exit full screen" : "Full screen", props.onToggleFullscreen)}
          {item(<Highlighter className="h-4 w-4" />, props.highlighterActive ? "Highlighter: On" : "Highlighter: Off", props.onToggleHighlighter, props.highlighterActive)}
          {item(<ZoomIn className="h-4 w-4" />, "Zoom in", props.onZoomIn)}
          {item(<ZoomOut className="h-4 w-4" />, "Zoom out", props.onZoomOut)}
          {props.pauseAllowed && item(props.paused ? <Play className="h-4 w-4" /> : <Pause className="h-4 w-4" />, props.paused ? "Resume" : "Pause", props.onTogglePause)}
          {item(<Keyboard className="h-4 w-4" />, "Keyboard shortcuts", props.onToggleHelp)}
          <div className="my-1 border-t border-slate-100" />
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              props.onSaveAndExit();
              setOpen(false);
            }}
            className="flex w-full items-center gap-3 px-4 py-2 text-left text-sm font-semibold text-slate-700 hover:bg-slate-50"
          >
            <LogOut className="h-4 w-4" />
            Save &amp; Exit
          </button>
        </div>
      )}
    </div>
  );
}
