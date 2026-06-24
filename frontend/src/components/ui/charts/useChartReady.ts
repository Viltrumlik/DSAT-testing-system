"use client";

import { useEffect, useState } from "react";

/** Recharts needs a measured DOM container; gate render until after mount
 *  to avoid zero-width charts and hydration mismatches. */
export function useChartReady(): boolean {
  const [ready, setReady] = useState(false);
  useEffect(() => setReady(true), []);
  return ready;
}
