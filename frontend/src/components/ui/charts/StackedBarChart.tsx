"use client";

import { BarChart, type BarChartProps } from "./BarChart";

/** Stacked variant of {@link BarChart}. Same data/series contract. */
export function StackedBarChart(props: Omit<BarChartProps, "stacked">) {
  return <BarChart {...props} stacked />;
}
