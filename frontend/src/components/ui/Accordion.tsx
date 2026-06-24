"use client";

import { useState } from "react";
import type { ReactNode } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/cn";

export type AccordionItem = {
  value: string;
  title: ReactNode;
  content: ReactNode;
};

export function Accordion({
  items,
  type = "single",
  defaultOpen = [],
  className,
}: {
  items: AccordionItem[];
  type?: "single" | "multiple";
  defaultOpen?: string[];
  className?: string;
}) {
  const [open, setOpen] = useState<string[]>(defaultOpen);

  const toggle = (value: string) => {
    setOpen((cur) => {
      const isOpen = cur.includes(value);
      if (type === "single") return isOpen ? [] : [value];
      return isOpen ? cur.filter((v) => v !== value) : [...cur, value];
    });
  };

  return (
    <div className={cn("divide-y divide-border overflow-hidden rounded-2xl border border-border bg-card", className)}>
      {items.map((item) => {
        const isOpen = open.includes(item.value);
        return (
          <div key={item.value}>
            <button
              type="button"
              aria-expanded={isOpen}
              onClick={() => toggle(item.value)}
              className="ds-ring flex w-full items-center justify-between gap-3 px-5 py-4 text-left text-sm font-semibold text-foreground transition-colors hover:bg-surface-2"
            >
              {item.title}
              <ChevronDown
                className={cn(
                  "h-4 w-4 shrink-0 text-muted-foreground transition-transform duration-200",
                  isOpen && "rotate-180",
                )}
              />
            </button>
            {isOpen ? (
              <div className="ds-anim-fade px-5 pb-5 text-sm text-muted-foreground">{item.content}</div>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}
