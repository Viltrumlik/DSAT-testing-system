"use client";

import {
  ResponsiveContainer,
  LineChart as RLineChart,
  Line,
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

export type LineChartProps = {
  data: Record<string, unknown>[];
  xKey: string;
  series: ChartSeries[];
  height?: number;
  loading?: boolean;
  valueFormatter?: (v: number) => string;
  yDomain?: [number | "auto", number | "auto"];
  emptyMessage?: { title?: string; description?: string };
};

export function LineChartImpl({
  data,
  xKey,
  series,
  height = 280,
  loading,
  valueFormatter,
  yDomain,
  emptyMessage,
}: LineChartProps) {
  const ready = useChartReady();
  if (loading || !ready) return <ChartSkeleton height={height} />;
  if (!data.length) return <ChartEmptyState height={height} {...emptyMessage} />;

  return (
    <div style={{ width: "100%", height }}>
      <ResponsiveContainer width="100%" height="100%">
        <RLineChart data={data} margin={{ top: 8, right: 8, left: -4, bottom: 0 }}>
          <CartesianGrid stroke={CHART_GRID} vertical={false} />
          <XAxis dataKey={xKey} tick={axisTick} axisLine={false} tickLine={false} dy={6} />
          <YAxis tick={axisTick} axisLine={false} tickLine={false} width={52} domain={yDomain} />
          <Tooltip
            content={<ChartTooltip valueFormatter={valueFormatter} />}
            cursor={{ stroke: CHART_GRID, strokeWidth: 1 }}
          />
          {series.map((s, i) => (
            <Line
              key={s.key}
              type="monotone"
              dataKey={s.key}
              name={s.label ?? s.key}
              stroke={seriesColor(i, s.color)}
              strokeWidth={2.5}
              dot={false}
              activeDot={{ r: 4 }}
            />
          ))}
        </RLineChart>
      </ResponsiveContainer>
    </div>
  );
}
