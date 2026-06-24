"use client";

import { cn } from "@/lib/cn";

interface MiniBarChartProps {
  /** Array of values, rendered left-to-right */
  data: number[];
  /** Labels shown below each bar (optional) */
  labels?: string[];
  /** Max bar height in px */
  height?: number;
  /** Bar accent color */
  barClass?: string;
  className?: string;
}

export function MiniBarChart({
  data,
  labels,
  height = 48,
  barClass = "bg-primary",
  className,
}: MiniBarChartProps) {
  const max = Math.max(...data, 1);

  return (
    <div className={cn("flex items-end gap-1.5", className)} style={{ height }}>
      {data.map((v, i) => {
        const pct = (v / max) * 100;
        return (
          <div key={i} className="flex flex-1 flex-col items-center gap-1">
            <div
              className={cn("w-full min-w-[6px] rounded-t-sm transition-all duration-500", barClass)}
              style={{ height: `${Math.max(pct, 4)}%` }}
            />
            {labels?.[i] && (
              <span className="text-[9px] font-bold text-muted-foreground">{labels[i]}</span>
            )}
          </div>
        );
      })}
    </div>
  );
}
