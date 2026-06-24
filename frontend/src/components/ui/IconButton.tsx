import { cn } from "@/lib/cn";
import type { ButtonHTMLAttributes, ReactNode } from "react";

export type IconButtonVariant = "default" | "ghost" | "muted";

const variantClass: Record<IconButtonVariant, string> = {
  default:
    "ms-icon-btn border border-border bg-card text-foreground shadow-sm hover:border-primary/30 hover:bg-surface-2",
  ghost:
    "ms-icon-btn-ghost border border-transparent text-muted-foreground hover:bg-surface-2",
  muted:
    "ms-icon-btn-ghost border border-transparent text-label-foreground hover:bg-surface-2/80",
};

export function IconButton({
  children,
  className,
  variant = "default",
  size = "md",
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  children: ReactNode;
  variant?: IconButtonVariant;
  size?: "sm" | "md";
}) {
  const sizeCls = size === "sm" ? "h-8 w-8 rounded-lg" : "h-10 w-10 rounded-xl";
  return (
    <button
      type="button"
      className={cn(
        "inline-flex items-center justify-center",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/90 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--background)] dark:focus-visible:ring-amber-400/55 dark:focus-visible:ring-offset-black",
        "disabled:pointer-events-none disabled:opacity-40",
        sizeCls,
        variantClass[variant],
        className,
      )}
      {...rest}
    >
      {children}
    </button>
  );
}
