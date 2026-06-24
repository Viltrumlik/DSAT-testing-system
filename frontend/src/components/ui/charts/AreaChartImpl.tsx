"use client";

import {
  ResponsiveContainer,
  AreaChart as RAreaChart,
  Area,
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

export type AreaChartProps = {
  data: Record<string, unknown>[];
  xKey: string;
  series: ChartSeries[];
  height?: number;
  loading?: boolean;
  valueFormatter?: (v: number) => string;
  emptyMessage?: { title?: string; description?: string };
};

export function AreaChartImpl({
  data,
  xKey,
  series,
  height = 280,
  loading,
  valueFormatter,
  emptyMessage,
}: AreaChartProps) {
  const ready = useChartReady();
  if (loading || !ready) return <ChartSkeleton height={height} />;
  if (!data.length) return <ChartEmptyState height={height} {...emptyMessage} />;

  return (
    <div style={{ width: "100%", height }}>
      <ResponsiveContainer width="100%" height="100%">
        <RAreaChart data={data} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
          <defs>
            {series.map((s, i) => {
              const color = seriesColor(i, s.color);
              return (
                <linearGradient key={s.key} id={`area-${s.key}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={color} stopOpacity={0.28} />
                  <stop offset="100%" stopColor={color} stopOpacity={0.02} />
                </linearGradient>
              );
            })}
          </defs>
          <CartesianGrid stroke={CHART_GRID} vertical={false} />
          <XAxis dataKey={xKey} tick={axisTick} axisLine={false} tickLine={false} dy={6} />
          <YAxis tick={axisTick} axisLine={false} tickLine={false} width={44} />
          <Tooltip content={<ChartTooltip valueFormatter={valueFormatter} />} cursor={{ stroke: CHART_GRID }} />
          {series.map((s, i) => {
            const color = seriesColor(i, s.color);
            return (
              <Area
                key={s.key}
                type="monotone"
                dataKey={s.key}
                name={s.label ?? s.key}
                stroke={color}
                strokeWidth={2.5}
                fill={`url(#area-${s.key})`}
              />
            );
          })}
        </RAreaChart>
      </ResponsiveContainer>
    </div>
  );
}
