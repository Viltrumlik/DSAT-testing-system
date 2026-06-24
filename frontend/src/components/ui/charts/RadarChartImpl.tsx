"use client";

import {
  ResponsiveContainer,
  RadarChart as RRadarChart,
  Radar,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Tooltip,
} from "recharts";
import { CHART_GRID, CHART_AXIS, seriesColor, type ChartSeries } from "./palette";
import { ChartTooltip } from "./ChartTooltip";
import { ChartSkeleton } from "./ChartSkeleton";
import { ChartEmptyState } from "./ChartEmptyState";
import { useChartReady } from "./useChartReady";

export type RadarChartProps = {
  data: Record<string, unknown>[];
  /** key on each datum holding the axis label (e.g. SAT domain name) */
  axisKey: string;
  series: ChartSeries[];
  height?: number;
  loading?: boolean;
  max?: number;
  valueFormatter?: (v: number) => string;
  emptyMessage?: { title?: string; description?: string };
};

/** SAT skill radar — one polygon per series across shared axes. */
export function RadarChartImpl({
  data,
  axisKey,
  series,
  height = 300,
  loading,
  max = 100,
  valueFormatter,
  emptyMessage,
}: RadarChartProps) {
  const ready = useChartReady();
  if (loading || !ready) return <ChartSkeleton height={height} />;
  if (!data.length) return <ChartEmptyState height={height} {...emptyMessage} />;

  return (
    <div style={{ width: "100%", height }}>
      <ResponsiveContainer width="100%" height="100%">
        <RRadarChart data={data} outerRadius="72%">
          <PolarGrid stroke={CHART_GRID} />
          <PolarAngleAxis dataKey={axisKey} tick={{ fill: CHART_AXIS, fontSize: 11 }} />
          <PolarRadiusAxis domain={[0, max]} tick={{ fill: CHART_AXIS, fontSize: 10 }} axisLine={false} />
          <Tooltip content={<ChartTooltip valueFormatter={valueFormatter} />} />
          {series.map((s, i) => {
            const color = seriesColor(i, s.color);
            return (
              <Radar
                key={s.key}
                dataKey={s.key}
                name={s.label ?? s.key}
                stroke={color}
                fill={color}
                fillOpacity={0.18}
                strokeWidth={2}
              />
            );
          })}
        </RRadarChart>
      </ResponsiveContainer>
    </div>
  );
}
