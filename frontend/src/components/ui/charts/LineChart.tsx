"use client";

import dynamic from "next/dynamic";
import { ChartSkeleton } from "./ChartSkeleton";

export type { LineChartProps } from "./LineChartImpl";

/** Recharts is loaded on demand (single shared async chunk) and never ships in
 *  a route's first-load JS. A skeleton fills the space while the chunk loads. */
export const LineChart = dynamic(
  () => import("./LineChartImpl").then((m) => m.LineChartImpl),
  { ssr: false, loading: () => <ChartSkeleton /> },
);
