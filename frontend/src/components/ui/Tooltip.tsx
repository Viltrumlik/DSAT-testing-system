"use client";

import { cn } from "@/lib/cn";
import type { ReactNode } from "react";

type Side = "top" | "bottom" | "left" | "right";

const sideClass: Record<Side, string> = {
  top: "bottom-full left-1/2 mb-2 -translate-x-1/2",
  bottom: "top-full left-1/2 mt-2 -translate-x-1/2",
  left: "right-full top-1/2 mr-2 -translate-y-1/2",
  right: "left-full top-1/2 ml-2 -translate-y-1/2",
};

/**
 * Hover + focus-visible tooltip. Keeps copy short for usability.
 */
export function Tooltip({
  content,
  children,
  side = "right",
  className,
}: {
  content: string;
  children: ReactNode;
  side?: Side;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "group/ds-tip relative inline-flex max-w-max shrink-0",
        className,
      )}
    >
      {children}
      <span
        role="tooltip"
        className={cn(
          "pointer-events-none absolute z-[300] max-w-[220px] rounded-lg border border-slate-200/90 bg-white/95 px-2.5 py-1.5 text-center text-[11px] font-semibold leading-snug text-slate-700 shadow-lg opacity-0 shadow-blue-500/10 transition-opacity duration-200",
          "invisible group-hover/ds-tip:visible group-hover/ds-tip:opacity-100",
          "group-focus-within/ds-tip:visible group-focus-within/ds-tip:opacity-100",
          "dark:border-slate-600 dark:bg-slate-900/95 dark:text-slate-200",
          sideClass[side],
        )}
      >
        {content}
      </span>
    </span>
  );
}
