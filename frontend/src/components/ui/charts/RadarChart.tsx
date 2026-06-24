"use client";

import dynamic from "next/dynamic";
import { ChartSkeleton } from "./ChartSkeleton";

export type { RadarChartProps } from "./RadarChartImpl";

/** Recharts is loaded on demand (single shared async chunk) and never ships in
 *  a route's first-load JS. A skeleton fills the space while the chunk loads. */
export const RadarChart = dynamic(
  () => import("./RadarChartImpl").then((m) => m.RadarChartImpl),
  { ssr: false, loading: () => <ChartSkeleton /> },
);
