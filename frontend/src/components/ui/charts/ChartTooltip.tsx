"use client";

import type { TooltipProps } from "recharts";

/** Themed tooltip shared by every chart wrapper. */
export function ChartTooltip({
  active,
  payload,
  label,
  valueFormatter,
}: TooltipProps<number, string> & { valueFormatter?: (v: number) => string }) {
  if (!active || !payload || payload.length === 0) return null;
  return (
    <div className="ds-chart-tooltip">
      {label !== undefined && label !== "" ? (
        <p className="mb-1 font-semibold text-foreground">{String(label)}</p>
      ) : null}
      <div className="flex flex-col gap-1">
        {payload.map((entry, i) => (
          <div key={i} className="flex items-center gap-2">
            <span
              className="h-2.5 w-2.5 shrink-0 rounded-sm"
              style={{ background: (entry.color as string) || "var(--chart-1)" }}
            />
            <span className="text-muted-foreground">{entry.name}</span>
            <span className="ds-num ml-auto font-semibold text-foreground">
              {typeof entry.value === "number"
                ? valueFormatter
                  ? valueFormatter(entry.value)
                  : entry.value
                : String(entry.value ?? "")}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
