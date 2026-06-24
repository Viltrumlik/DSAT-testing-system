"use client";

interface ModuleTransitionOverlayProps {
  toModuleOrder: number;
  subjectLabel: string;
}

/** Full-screen "Continuing to Module N" interstitial shown during M1→M2. */
export function ModuleTransitionOverlay({ toModuleOrder, subjectLabel }: ModuleTransitionOverlayProps) {
  return (
    <div className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-white">
      <div className="h-10 w-10 animate-spin rounded-full border-4 border-slate-200 border-t-blue-600" />
      <h2 className="mt-6 text-xl font-bold tracking-tight text-slate-900">Continuing to Module {toModuleOrder}</h2>
      <p className="mt-2 font-medium text-slate-500">{subjectLabel}</p>
    </div>
  );
}
