import { cn } from "@/lib/cn";

/** Placeholder shown while chart data loads. */
export function ChartSkeleton({ height = 280, className }: { height?: number; className?: string }) {
  return (
    <div
      className={cn("flex w-full items-end gap-2 px-2", className)}
      style={{ height }}
      aria-hidden
    >
      {[40, 65, 50, 80, 55, 72, 48, 88].map((h, i) => (
        <div key={i} className="ds-skeleton flex-1 rounded-md" style={{ height: `${h}%` }} />
      ))}
    </div>
  );
}
