"use client";

import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

export type Segment<T extends string> = { value: T; label: ReactNode; icon?: React.ElementType };

export function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
  size = "md",
  className,
  ariaLabel,
}: {
  options: Segment<T>[];
  value: T;
  onChange: (value: T) => void;
  size?: "sm" | "md";
  className?: string;
  ariaLabel?: string;
}) {
  return (
    <div
      role="radiogroup"
      aria-label={ariaLabel}
      className={cn("inline-flex items-center gap-1 rounded-xl bg-surface-2 p-1", className)}
    >
      {options.map((opt) => {
        const active = opt.value === value;
        const Icon = opt.icon;
        return (
          <button
            key={opt.value}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => onChange(opt.value)}
            className={cn(
              "ds-ring inline-flex items-center justify-center gap-1.5 rounded-lg font-semibold transition-colors",
              size === "sm" ? "px-2.5 py-1 text-[13px]" : "px-3.5 py-1.5 text-sm",
              active ? "bg-card text-foreground shadow-card" : "text-muted-foreground hover:text-foreground",
            )}
          >
            {Icon ? <Icon className="h-4 w-4" /> : null}
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}
