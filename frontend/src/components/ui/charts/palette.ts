/**
 * Token-driven chart palette. Values are CSS custom properties, so charts
 * adapt to light/dark automatically without re-rendering. Swapping the
 * underlying chart library later only touches files in this folder.
 */
export const CHART_COLORS = [
  "var(--chart-1)",
  "var(--chart-2)",
  "var(--chart-3)",
  "var(--chart-4)",
  "var(--chart-5)",
  "var(--chart-6)",
] as const;

export const CHART_GRID = "var(--chart-grid)";
export const CHART_AXIS = "var(--chart-axis)";

export function seriesColor(index: number, override?: string): string {
  return override ?? CHART_COLORS[index % CHART_COLORS.length];
}

/** Shared series descriptor used across every chart wrapper. */
export type ChartSeries = {
  key: string;
  label?: string;
  color?: string;
};

export const axisTick = { fill: CHART_AXIS, fontSize: 12 } as const;
