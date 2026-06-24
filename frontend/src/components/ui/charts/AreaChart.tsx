"use client";

import dynamic from "next/dynamic";
import { ChartSkeleton } from "./ChartSkeleton";

export type { AreaChartProps } from "./AreaChartImpl";

/** Recharts is loaded on demand (single shared async chunk) and never ships in
 *  a route's first-load JS. A skeleton fills the space while the chunk loads. */
export const AreaChart = dynamic(
  () => import("./AreaChartImpl").then((m) => m.AreaChartImpl),
  { ssr: false, loading: () => <ChartSkeleton /> },
);
