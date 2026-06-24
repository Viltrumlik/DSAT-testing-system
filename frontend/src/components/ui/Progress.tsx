import { cn } from "@/lib/cn";

export type ProgressTone = "primary" | "accent" | "success" | "warning";

const toneClass: Record<ProgressTone, string> = {
  primary: "bg-primary",
  accent: "bg-accent",
  success: "bg-success",
  warning: "bg-warning",
};

export function Progress({
  value,
  tone = "primary",
  size = "md",
  className,
  label,
}: {
  /** 0–100 */
  value: number;
  tone?: ProgressTone;
  size?: "sm" | "md";
  className?: string;
  /** Optional aria label for screen readers */
  label?: string;
}) {
  const clamped = Math.max(0, Math.min(100, value));
  return (
    <div
      role="progressbar"
      aria-valuenow={Math.round(clamped)}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={label}
      className={cn(
        "w-full overflow-hidden rounded-full bg-surface-3",
        size === "sm" ? "h-1.5" : "h-2.5",
        className,
      )}
    >
      <div
        className={cn("h-full rounded-full transition-[width] duration-500 ease-[var(--ds-ease-premium)]", toneClass[tone])}
        style={{ width: `${clamped}%` }}
      />
    </div>
  );
}
