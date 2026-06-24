"use client";

import { ResponsiveContainer, PieChart, Pie, Cell, Tooltip } from "recharts";
import { seriesColor } from "./palette";
import { ChartTooltip } from "./ChartTooltip";
import { ChartSkeleton } from "./ChartSkeleton";
import { ChartEmptyState } from "./ChartEmptyState";
import { useChartReady } from "./useChartReady";

export type DonutDatum = { name: string; value: number; color?: string };

export type DonutChartProps = {
  data: DonutDatum[];
  height?: number;
  loading?: boolean;
  thickness?: number;
  centerLabel?: string;
  centerValue?: string | number;
  valueFormatter?: (v: number) => string;
  emptyMessage?: { title?: string; description?: string };
};

export function DonutChartImpl({
  data,
  height = 280,
  loading,
  thickness = 28,
  centerLabel,
  centerValue,
  valueFormatter,
  emptyMessage,
}: DonutChartProps) {
  const ready = useChartReady();
  if (loading || !ready) return <ChartSkeleton height={height} />;
  if (!data.length || data.every((d) => !d.value)) return <ChartEmptyState height={height} {...emptyMessage} />;

  const outer = Math.min(height / 2 - 8, 120);
  const inner = outer - thickness;

  return (
    <div className="relative" style={{ width: "100%", height }}>
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie
            data={data}
            dataKey="value"
            nameKey="name"
            innerRadius={inner}
            outerRadius={outer}
            paddingAngle={2}
            stroke="var(--card)"
            strokeWidth={2}
          >
            {data.map((d, i) => (
              <Cell key={d.name} fill={seriesColor(i, d.color)} />
            ))}
          </Pie>
          <Tooltip content={<ChartTooltip valueFormatter={valueFormatter} />} />
        </PieChart>
      </ResponsiveContainer>
      {centerValue !== undefined || centerLabel ? (
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center text-center">
          {centerValue !== undefined ? (
            <span className="ds-num text-2xl font-extrabold text-foreground">{centerValue}</span>
          ) : null}
          {centerLabel ? <span className="ds-overline mt-0.5">{centerLabel}</span> : null}
        </div>
      ) : null}
    </div>
  );
}
