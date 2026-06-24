import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/cn";

/**
 * StudioEmptyState — canonical zero-content placeholder for studio list views.
 *
 * Usage:
 *   <StudioEmptyState
 *     icon={BookOpen}
 *     title="No questions yet"
 *     body="Click 'Add question' to create the first one."
 *     action={<button ...>Add question</button>}
 *   />
 */
export function StudioEmptyState({
  icon: Icon,
  title,
  body,
  action,
  className,
}: {
  icon?: LucideIcon;
  title: string;
  body?: string;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-3 p-12 text-center",
        className,
      )}
    >
      {Icon && (
        <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-surface-2">
          <Icon className="h-6 w-6 text-muted-foreground/40" aria-hidden />
        </div>
      )}
      <p className="font-semibold text-foreground">{title}</p>
      {body && <p className="max-w-xs text-sm text-muted-foreground">{body}</p>}
      {action && <div className="mt-1">{action}</div>}
    </div>
  );
}
