"use client";

import dynamic from "next/dynamic";
import { ChartSkeleton } from "./ChartSkeleton";

export type { DonutChartProps, DonutDatum } from "./DonutChartImpl";

/** Recharts is loaded on demand (single shared async chunk) and never ships in
 *  a route's first-load JS. A skeleton fills the space while the chunk loads. */
export const DonutChart = dynamic(
  () => import("./DonutChartImpl").then((m) => m.DonutChartImpl),
  { ssr: false, loading: () => <ChartSkeleton /> },
);
