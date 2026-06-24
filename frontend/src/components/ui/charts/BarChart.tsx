"use client";

import dynamic from "next/dynamic";
import { ChartSkeleton } from "./ChartSkeleton";

export type { BarChartProps } from "./BarChartImpl";

/** Recharts is loaded on demand (single shared async chunk) and never ships in
 *  a route's first-load JS. A skeleton fills the space while the chunk loads. */
export const BarChart = dynamic(
  () => import("./BarChartImpl").then((m) => m.BarChartImpl),
  { ssr: false, loading: () => <ChartSkeleton /> },
);
