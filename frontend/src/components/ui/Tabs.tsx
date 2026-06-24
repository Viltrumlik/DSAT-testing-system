"use client";

import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

export type TabItem = {
  value: string;
  label: ReactNode;
  icon?: React.ElementType;
  badge?: ReactNode;
};

export type TabsProps = {
  tabs: TabItem[];
  value: string;
  onValueChange: (value: string) => void;
  variant?: "underline" | "pill";
  className?: string;
  "aria-label"?: string;
};

/** Headless-ish tab bar; the caller renders the active panel. */
export function Tabs({
  tabs,
  value,
  onValueChange,
  variant = "underline",
  className,
  ...rest
}: TabsProps) {
  if (variant === "pill") {
    return (
      <div
        role="tablist"
        aria-label={rest["aria-label"]}
        className={cn("inline-flex items-center gap-1 rounded-xl bg-surface-2 p-1", className)}
      >
        {tabs.map((t) => {
          const active = t.value === value;
          const Icon = t.icon;
          return (
            <button
              key={t.value}
              role="tab"
              aria-selected={active}
              onClick={() => onValueChange(t.value)}
              className={cn(
                "ds-ring inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-semibold transition-colors",
                active
                  ? "bg-card text-foreground shadow-card"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {Icon ? <Icon className="h-4 w-4" /> : null}
              {t.label}
              {t.badge}
            </button>
          );
        })}
      </div>
    );
  }

  return (
    <div
      role="tablist"
      aria-label={rest["aria-label"]}
      className={cn("flex items-center gap-1 border-b border-border", className)}
    >
      {tabs.map((t) => {
        const active = t.value === value;
        const Icon = t.icon;
        return (
          <button
            key={t.value}
            role="tab"
            aria-selected={active}
            onClick={() => onValueChange(t.value)}
            className={cn(
              "ds-ring relative inline-flex items-center gap-1.5 px-3 py-2.5 text-sm font-semibold transition-colors",
              active ? "text-primary" : "text-muted-foreground hover:text-foreground",
            )}
          >
            {Icon ? <Icon className="h-4 w-4" /> : null}
            {t.label}
            {t.badge}
            {active ? (
              <span className="absolute inset-x-2 -bottom-px h-0.5 rounded-full bg-primary" />
            ) : null}
          </button>
        );
      })}
    </div>
  );
}
