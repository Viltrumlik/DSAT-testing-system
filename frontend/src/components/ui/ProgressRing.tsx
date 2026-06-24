"use client";

import { cn } from "@/lib/cn";

interface ProgressRingProps {
  /** 0–100 */
  value: number;
  /** px */
  size?: number;
  /** px */
  strokeWidth?: number;
  /** Tailwind text color for the filled arc, e.g. "text-primary" */
  color?: string;
  /** Show percentage label in the center */
  showLabel?: boolean;
  className?: string;
  children?: React.ReactNode;
}

export function ProgressRing({
  value,
  size = 64,
  strokeWidth = 5,
  color = "text-primary",
  showLabel = true,
  className,
  children,
}: ProgressRingProps) {
  const clamped = Math.max(0, Math.min(100, value));
  const r = (size - strokeWidth) / 2;
  const circ = 2 * Math.PI * r;
  const offset = circ - (clamped / 100) * circ;

  return (
    <div className={cn("relative inline-flex items-center justify-center", className)} style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        {/* Track */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="currentColor"
          strokeWidth={strokeWidth}
          className="text-border"
        />
        {/* Fill */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="currentColor"
          strokeWidth={strokeWidth}
          strokeDasharray={circ}
          strokeDashoffset={offset}
          strokeLinecap="round"
          className={cn("transition-all duration-700 ease-out", color)}
        />
      </svg>
      {/* Center content */}
      <div className="absolute inset-0 flex items-center justify-center">
        {children ?? (showLabel && (
          <span className="text-sm font-black tabular-nums text-foreground">{Math.round(clamped)}%</span>
        ))}
      </div>
    </div>
  );
}
