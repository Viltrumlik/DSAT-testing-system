"use client";
import { AlertTriangle } from "lucide-react";

/** Blocking overlay shown in a duplicate tab of the same attempt. */
export function MultiTabOverlay({ onContinue }: { onContinue: () => void }) {
  return (
    <div className="fixed inset-0 z-[70] flex flex-col items-center justify-center bg-white px-6 text-center">
      <AlertTriangle className="h-12 w-12 text-amber-500" />
      <h2 className="mt-5 text-xl font-bold tracking-tight text-slate-900">This exam is open in another tab</h2>
      <p className="mt-2 max-w-md font-medium text-slate-500">
        To keep your answers and timer consistent, the exam should run in only one tab. Close the other tab, or continue
        here (the other tab will be locked).
      </p>
      <button
        type="button"
        onClick={onContinue}
        className="mt-6 rounded-xl bg-blue-600 px-5 py-3 font-bold text-white hover:bg-blue-700"
      >
        Continue in this tab
      </button>
    </div>
  );
}
