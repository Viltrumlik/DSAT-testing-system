"use client";

export default function ErrorPanel({
  title = "Something went wrong",
  message,
  actionLabel,
  onAction,
}: {
  title?: string;
  message: string;
  actionLabel?: string;
  onAction?: () => void;
}) {
  return (
    <div className="rounded-2xl border border-border bg-surface-2 p-4">
      <p className="text-sm font-extrabold text-foreground">{title}</p>
      <p className="mt-1 text-sm text-muted-foreground">{message}</p>
      {actionLabel && onAction ? (
        <button
          type="button"
          onClick={onAction}
          className="mt-3 rounded-xl border border-border bg-card px-4 py-2 text-sm font-extrabold hover:bg-surface-2"
        >
          {actionLabel}
        </button>
      ) : null}
    </div>
  );
}

