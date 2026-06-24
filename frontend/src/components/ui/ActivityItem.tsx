"use client";

import { cn } from "@/lib/cn";
import type { LucideIcon } from "lucide-react";

interface ActivityItemProps {
  icon: LucideIcon;
  iconColor?: string;
  title: string;
  meta?: string;
  time?: string;
  className?: string;
}

export function ActivityItem({ icon: Icon, iconColor = "text-primary bg-primary/10", title, meta, time, className }: ActivityItemProps) {
  return (
    <div className={cn("flex items-start gap-3 py-3", className)}>
      <div className={cn("mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg", iconColor)}>
        <Icon className="h-4 w-4" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold text-foreground leading-snug">{title}</p>
        {meta && <p className="text-xs text-muted-foreground">{meta}</p>}
      </div>
      {time && <span className="shrink-0 text-[11px] font-medium text-muted-foreground">{time}</span>}
    </div>
  );
}
