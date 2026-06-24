"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import { cn } from "@/lib/cn";

/** Compact pager. `page` and `pageCount` are 1-based. */
export function Pagination({
  page,
  pageCount,
  onPageChange,
  className,
}: {
  page: number;
  pageCount: number;
  onPageChange: (page: number) => void;
  className?: string;
}) {
  if (pageCount <= 1) return null;

  const pages = pageWindow(page, pageCount);

  const btn =
    "ds-ring inline-flex h-9 min-w-9 items-center justify-center rounded-lg border px-2 text-sm font-semibold transition-colors disabled:opacity-40 disabled:pointer-events-none";

  return (
    <nav className={cn("flex items-center gap-1.5", className)} aria-label="Pagination">
      <button
        className={cn(btn, "border-border bg-card text-muted-foreground hover:bg-surface-2")}
        onClick={() => onPageChange(page - 1)}
        disabled={page <= 1}
        aria-label="Previous page"
      >
        <ChevronLeft className="h-4 w-4" />
      </button>
      {pages.map((p, i) =>
        p === "…" ? (
          <span key={`gap-${i}`} className="px-1 text-sm text-label-foreground">
            …
          </span>
        ) : (
          <button
            key={p}
            onClick={() => onPageChange(p)}
            aria-current={p === page ? "page" : undefined}
            className={cn(
              btn,
              p === page
                ? "border-primary bg-primary text-primary-foreground"
                : "border-border bg-card text-foreground hover:bg-surface-2",
            )}
          >
            {p}
          </button>
        ),
      )}
      <button
        className={cn(btn, "border-border bg-card text-muted-foreground hover:bg-surface-2")}
        onClick={() => onPageChange(page + 1)}
        disabled={page >= pageCount}
        aria-label="Next page"
      >
        <ChevronRight className="h-4 w-4" />
      </button>
    </nav>
  );
}

function pageWindow(page: number, count: number): (number | "…")[] {
  if (count <= 7) return Array.from({ length: count }, (_, i) => i + 1);
  const out: (number | "…")[] = [1];
  const start = Math.max(2, page - 1);
  const end = Math.min(count - 1, page + 1);
  if (start > 2) out.push("…");
  for (let i = start; i <= end; i++) out.push(i);
  if (end < count - 1) out.push("…");
  out.push(count);
  return out;
}
