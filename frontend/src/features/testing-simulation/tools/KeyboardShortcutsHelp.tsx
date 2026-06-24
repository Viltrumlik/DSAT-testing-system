"use client";
import { X } from "lucide-react";
import { SHORTCUTS } from "./useKeyboardShortcuts";

/** Modal listing keyboard shortcuts (toggled with `?`). */
export function KeyboardShortcutsHelp({ onClose }: { onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-[55] flex items-center justify-center bg-black/30" onClick={onClose}>
      <div className="w-full max-w-sm rounded-2xl bg-white p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-bold tracking-tight text-slate-900">Keyboard shortcuts</h3>
          <button type="button" onClick={onClose} className="text-slate-400 hover:text-slate-700">
            <X className="h-5 w-5" />
          </button>
        </div>
        <ul className="space-y-2">
          {SHORTCUTS.map((s) => (
            <li key={s.keys} className="flex items-center justify-between">
              <span className="text-sm text-slate-600">{s.action}</span>
              <kbd className="rounded-md border border-slate-300 bg-slate-50 px-2 py-0.5 font-mono text-xs font-bold text-slate-700">{s.keys}</kbd>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
