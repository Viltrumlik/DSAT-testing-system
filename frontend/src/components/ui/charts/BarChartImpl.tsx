"use client";

import {
  ResponsiveContainer,
  BarChart as RBarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from "recharts";
import { CHART_GRID, axisTick, seriesColor, type ChartSeries } from "./palette";
import { ChartTooltip } from "./ChartTooltip";
import { ChartSkeleton } from "./ChartSkeleton";
import { ChartEmptyState } from "./ChartEmptyState";
import { useChartReady } from "./useChartReady";

export type BarChartProps = {
  data: Record<string, unknown>[];
  xKey: string;
  series: ChartSeries[];
  height?: number;
  loading?: boolean;
  stacked?: boolean;
  valueFormatter?: (v: number) => string;
  emptyMessage?: { title?: string; description?: string };
};

/** Grouped (or stacked) bar chart. */
export function BarChartImpl({
  data,
  xKey,
  series,
  height = 280,
  loading,
  stacked = false,
  valueFormatter,
  emptyMessage,
}: BarChartProps) {
  const ready = useChartReady();
  if (loading || !ready) return <ChartSkeleton height={height} />;
  if (!data.length) return <ChartEmptyState height={height} {...emptyMessage} />;

  const lastIdx = series.length - 1;

  return (
    <div style={{ width: "100%", height }}>
      <ResponsiveContainer width="100%" height="100%">
        <RBarChart data={data} margin={{ top: 8, right: 8, left: -12, bottom: 0 }} barGap={4}>
          <CartesianGrid stroke={CHART_GRID} vertical={false} />
          <XAxis dataKey={xKey} tick={axisTick} axisLine={false} tickLine={false} dy={6} />
          <YAxis tick={axisTick} axisLine={false} tickLine={false} width={44} />
          <Tooltip content={<ChartTooltip valueFormatter={valueFormatter} />} cursor={{ fill: CHART_GRID }} />
          {series.map((s, i) => (
            <Bar
              key={s.key}
              dataKey={s.key}
              name={s.label ?? s.key}
              fill={seriesColor(i, s.color)}
              stackId={stacked ? "stack" : undefined}
              radius={stacked ? (i === lastIdx ? [4, 4, 0, 0] : [0, 0, 0, 0]) : [4, 4, 0, 0]}
              maxBarSize={48}
            />
          ))}
        </RBarChart>
      </ResponsiveContainer>
    </div>
  );
}
