"use client";

import { cn } from "@/lib/cn";

interface PageHeaderProps {
  eyebrow?: string;
  title: string;
  description?: string;
  actions?: React.ReactNode;
  className?: string;
}

export function PageHeader({ eyebrow, title, description, actions, className }: PageHeaderProps) {
  return (
    <div className={cn("mb-8", className)}>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          {eyebrow && (
            <p className="mb-1.5 text-[11px] font-bold uppercase tracking-widest text-primary">{eyebrow}</p>
          )}
          <h1 className="text-2xl font-black tracking-tight text-foreground">{title}</h1>
          {description && (
            <p className="mt-2 max-w-xl text-sm leading-relaxed text-muted-foreground">{description}</p>
          )}
        </div>
        {actions && <div className="flex items-center gap-2 shrink-0">{actions}</div>}
      </div>
    </div>
  );
}
