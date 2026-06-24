import type { LucideIcon } from "lucide-react";
import { ArrowUpRight, ArrowDownRight } from "lucide-react";
import { cn } from "@/lib/cn";

export type StatProps = {
  label: string;
  value: React.ReactNode;
  icon?: LucideIcon;
  /** Signed change; positive renders as growth (success), negative as a gentle warning tone */
  delta?: number;
  deltaSuffix?: string;
  hint?: string;
  className?: string;
  onClick?: () => void;
};

/** Premium metric tile. Delta is framed positively — growth highlighted,
 *  dips shown in a soft (non-punishing) tone. */
export function Stat({
  label,
  value,
  icon: Icon,
  delta,
  deltaSuffix = "",
  hint,
  className,
  onClick,
}: StatProps) {
  const hasDelta = typeof delta === "number" && delta !== 0;
  const up = (delta ?? 0) > 0;
  const Wrapper = onClick ? "button" : "div";
  return (
    <Wrapper
      onClick={onClick}
      className={cn(
        "flex flex-col gap-3 rounded-2xl border border-border bg-card p-5 text-left shadow-card",
        onClick && "ds-ring transition-[border-color,box-shadow] hover:border-border-strong hover:shadow-pop",
        className,
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="ds-overline">{label}</span>
        {Icon ? (
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary-soft text-primary">
            <Icon className="h-4 w-4" />
          </span>
        ) : null}
      </div>
      <div className="flex items-end justify-between gap-2">
        <span className="ds-num text-[28px] font-extrabold leading-none tracking-tight text-foreground">
          {value}
        </span>
        {hasDelta ? (
          <span
            className={cn(
              "inline-flex items-center gap-0.5 rounded-md px-1.5 py-0.5 text-xs font-bold",
              up ? "bg-success-soft text-success-foreground" : "bg-warning-soft text-warning-foreground",
            )}
          >
            {up ? <ArrowUpRight className="h-3.5 w-3.5" /> : <ArrowDownRight className="h-3.5 w-3.5" />}
            {Math.abs(delta as number)}
            {deltaSuffix}
          </span>
        ) : null}
      </div>
      {hint ? <p className="text-[13px] text-muted-foreground">{hint}</p> : null}
    </Wrapper>
  );
}
