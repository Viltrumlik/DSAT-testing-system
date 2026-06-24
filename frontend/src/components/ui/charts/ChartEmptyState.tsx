import { LineChart as LineChartIcon } from "lucide-react";
import { cn } from "@/lib/cn";

/** Encouraging empty state for charts with no data yet. */
export function ChartEmptyState({
  height = 280,
  title = "No data yet",
  description = "Complete a practice set to start building your trend.",
  className,
}: {
  height?: number;
  title?: string;
  description?: string;
  className?: string;
}) {
  return (
    <div
      className={cn("flex flex-col items-center justify-center gap-2 text-center", className)}
      style={{ height }}
    >
      <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-primary-soft text-primary">
        <LineChartIcon className="h-5 w-5" />
      </div>
      <p className="text-sm font-semibold text-foreground">{title}</p>
      <p className="max-w-xs text-[13px] text-muted-foreground">{description}</p>
    </div>
  );
}
