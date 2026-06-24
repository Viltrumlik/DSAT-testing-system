import { cn } from "@/lib/cn";
import type { HTMLAttributes, ReactNode } from "react";

/** Legacy names (brand/live) kept for back-compat with pre-rebuild pages;
 *  semantic names are preferred going forward. */
export type BadgeVariant =
  | "brand"
  | "primary"
  | "neutral"
  | "outline"
  | "success"
  | "warning"
  | "danger"
  | "info"
  | "accent"
  | "live";

const variantClass: Record<BadgeVariant, string> = {
  brand: "border-primary/20 bg-primary-soft text-primary",
  primary: "border-primary/20 bg-primary-soft text-primary",
  neutral: "border-border bg-surface-2 text-muted-foreground",
  outline: "border-border bg-transparent text-muted-foreground",
  success: "border-success/20 bg-success-soft text-success-foreground",
  warning: "border-warning/20 bg-warning-soft text-warning-foreground",
  danger: "border-danger/20 bg-danger-soft text-danger-foreground",
  info: "border-info/20 bg-info-soft text-info-foreground",
  accent: "border-accent/20 bg-accent-soft text-accent",
  live: "border-info/20 bg-info-soft text-info-foreground",
};

const dotClass: Record<BadgeVariant, string> = {
  brand: "bg-primary",
  primary: "bg-primary",
  neutral: "bg-muted-foreground",
  outline: "bg-muted-foreground",
  success: "bg-success",
  warning: "bg-warning",
  danger: "bg-danger",
  info: "bg-info",
  accent: "bg-accent",
  live: "bg-info",
};

export function Badge({
  children,
  variant = "neutral",
  className,
  dot,
  ...rest
}: HTMLAttributes<HTMLSpanElement> & {
  children: ReactNode;
  variant?: BadgeVariant;
  /** Leading status dot (pulses on `live`) */
  dot?: boolean;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-semibold leading-5",
        variantClass[variant],
        className,
      )}
      {...rest}
    >
      {dot ? (
        <span className="relative flex h-1.5 w-1.5">
          {variant === "live" ? (
            <span className={cn("absolute inline-flex h-full w-full animate-ping rounded-full opacity-60", dotClass[variant])} />
          ) : null}
          <span className={cn("relative inline-flex h-1.5 w-1.5 rounded-full", dotClass[variant])} />
        </span>
      ) : null}
      {children}
    </span>
  );
}
