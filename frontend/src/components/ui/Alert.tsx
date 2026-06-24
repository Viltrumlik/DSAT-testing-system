import type { ReactNode } from "react";
import { Info, CheckCircle2, AlertTriangle, AlertCircle, X } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/cn";

export type AlertTone = "info" | "success" | "warning" | "danger" | "neutral";

const toneClass: Record<AlertTone, string> = {
  info: "border-info/25 bg-info-soft text-info-foreground",
  success: "border-success/25 bg-success-soft text-success-foreground",
  warning: "border-warning/25 bg-warning-soft text-warning-foreground",
  danger: "border-danger/25 bg-danger-soft text-danger-foreground",
  neutral: "border-border bg-surface-2 text-foreground",
};

const toneIcon: Record<AlertTone, LucideIcon> = {
  info: Info,
  success: CheckCircle2,
  warning: AlertTriangle,
  danger: AlertCircle,
  neutral: Info,
};

export function Alert({
  tone = "info",
  title,
  children,
  icon,
  onClose,
  className,
}: {
  tone?: AlertTone;
  title?: ReactNode;
  children?: ReactNode;
  icon?: ReactNode;
  onClose?: () => void;
  className?: string;
}) {
  const Icon = toneIcon[tone];
  return (
    <div
      role="status"
      className={cn("flex items-start gap-3 rounded-xl border p-4", toneClass[tone], className)}
    >
      <span className="mt-0.5 shrink-0">{icon ?? <Icon className="h-[18px] w-[18px]" />}</span>
      <div className="min-w-0 flex-1">
        {title ? <p className="text-sm font-semibold">{title}</p> : null}
        {children ? (
          <div className={cn("text-[13px] leading-relaxed opacity-90", !!title && "mt-0.5")}>{children}</div>
        ) : null}
      </div>
      {onClose ? (
        <button
          type="button"
          onClick={onClose}
          aria-label="Dismiss"
          className="ds-ring -m-1 shrink-0 rounded-md p-1 opacity-70 transition-opacity hover:opacity-100"
        >
          <X className="h-4 w-4" />
        </button>
      ) : null}
    </div>
  );
}
