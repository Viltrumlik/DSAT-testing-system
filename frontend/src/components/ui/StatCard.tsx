"use client";

import { cn } from "@/lib/cn";
import type { LucideIcon } from "lucide-react";
import { TrendingUp, TrendingDown, Minus } from "lucide-react";

type Trend = "up" | "down" | "neutral";

interface StatCardProps {
  label: string;
  value: string | number;
  icon?: LucideIcon;
  /** Subtitle text below value */
  sub?: string;
  /** Percentage change */
  change?: number;
  trend?: Trend;
  /** Accent color class, e.g. "text-blue-600 bg-blue-50" */
  accent?: string;
  className?: string;
  onClick?: () => void;
}

const trendConfig: Record<Trend, { icon: LucideIcon; color: string }> = {
  up: { icon: TrendingUp, color: "text-emerald-600 bg-emerald-50 dark:text-emerald-400 dark:bg-emerald-950/40" },
  down: { icon: TrendingDown, color: "text-red-600 bg-red-50 dark:text-red-400 dark:bg-red-950/40" },
  neutral: { icon: Minus, color: "text-slate-500 bg-slate-100 dark:text-slate-400 dark:bg-slate-800" },
};

export function StatCard({
  label,
  value,
  icon: Icon,
  sub,
  change,
  trend,
  accent = "text-primary bg-primary/10",
  className,
  onClick,
}: StatCardProps) {
  const Tag = onClick ? "button" : "div";
  const t = trend ? trendConfig[trend] : null;
  const TrendIcon = t?.icon;

  return (
    <Tag
      type={onClick ? "button" : undefined}
      onClick={onClick}
      className={cn(
        "relative overflow-hidden rounded-2xl border border-border bg-card p-5 text-left transition-all",
        onClick && "cursor-pointer hover:border-primary/25 hover:shadow-md active:scale-[0.99]",
        className,
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">{label}</p>
          <p className="mt-1 text-2xl font-black tabular-nums text-foreground leading-none">{value}</p>
          {sub && <p className="mt-1.5 text-xs font-medium text-muted-foreground">{sub}</p>}
        </div>
        {Icon && (
          <div className={cn("flex h-10 w-10 shrink-0 items-center justify-center rounded-xl", accent)}>
            <Icon className="h-5 w-5" />
          </div>
        )}
      </div>
      {change !== undefined && t && TrendIcon && (
        <div className="mt-3 flex items-center gap-1.5">
          <span className={cn("inline-flex items-center gap-1 rounded-lg px-2 py-0.5 text-[11px] font-bold", t.color)}>
            <TrendIcon className="h-3 w-3" />
            {Math.abs(change)}%
          </span>
          <span className="text-[11px] text-muted-foreground">vs last week</span>
        </div>
      )}
    </Tag>
  );
}
