import type { ReactNode } from "react";
import { cn } from "@/lib/cn";
import { seriesColor, type ChartSeries } from "./palette";

export type ChartCardProps = {
  title?: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  /** When provided, renders a token-colored legend below the header. */
  legend?: ChartSeries[];
  className?: string;
  children: ReactNode;
};

/** Framed container for any chart: header, optional legend, body. */
export function ChartCard({ title, description, actions, legend, className, children }: ChartCardProps) {
  return (
    <section className={cn("flex flex-col rounded-2xl border border-border bg-card p-5 shadow-card", className)}>
      {(title || actions) && (
        <header className="mb-4 flex items-start justify-between gap-3">
          <div className="min-w-0">
            {title ? <h3 className="ds-h4">{title}</h3> : null}
            {description ? <p className="mt-0.5 text-[13px] text-muted-foreground">{description}</p> : null}
          </div>
          {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
        </header>
      )}
      {legend && legend.length > 0 ? (
        <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1.5">
          {legend.map((s, i) => (
            <span key={s.key} className="inline-flex items-center gap-1.5 text-[13px] text-muted-foreground">
              <span className="h-2.5 w-2.5 rounded-sm" style={{ background: seriesColor(i, s.color) }} />
              {s.label ?? s.key}
            </span>
          ))}
        </div>
      ) : null}
      <div className="min-w-0 flex-1">{children}</div>
    </section>
  );
}
