"use client";

/** Centered loading spinner shown while the attempt boots. */
export function LoadingScreen({ label = "Loading exam…" }: { label?: string }) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-white">
      <div className="h-10 w-10 animate-spin rounded-full border-4 border-slate-200 border-t-blue-600" />
      <p className="mt-5 font-medium text-slate-500">{label}</p>
    </div>
  );
}

interface ErrorScreenProps {
  title: string;
  message: string;
  /** When omitted (e.g. for students) no recovery button is shown. */
  actionLabel?: string;
  onAction?: () => void;
  /** Optional secondary line, e.g. a hint for students. */
  hint?: string;
}

/** Error screen. The recovery action is only rendered when provided (admin-only). */
export function ErrorScreen({ title, message, actionLabel, onAction, hint }: ErrorScreenProps) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-white px-6">
      <h2 className="text-center text-xl font-bold tracking-tight text-slate-900">{title}</h2>
      <p className="mt-3 max-w-md text-center font-medium text-slate-500">{message}</p>
      {hint && <p className="mt-2 max-w-md text-center text-sm text-slate-400">{hint}</p>}
      {actionLabel && onAction && (
        <button
          type="button"
          onClick={onAction}
          className="mt-6 inline-flex items-center justify-center rounded-xl bg-emerald-600 px-5 py-3 font-bold text-white transition-colors hover:bg-emerald-700"
        >
          {actionLabel}
        </button>
      )}
    </div>
  );
}

/** Scoring interstitial shown while the backend finalizes the score. */
export function ScoringScreen({ notice }: { notice?: string | null }) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-white">
      <div className="h-10 w-10 animate-spin rounded-full border-4 border-slate-200 border-t-emerald-600" />
      <h2 className="mt-6 text-xl font-bold tracking-tight text-slate-900">Scoring your exam…</h2>
      <p className="mt-2 font-medium text-slate-500">{notice || "This only takes a moment."}</p>
    </div>
  );
}
