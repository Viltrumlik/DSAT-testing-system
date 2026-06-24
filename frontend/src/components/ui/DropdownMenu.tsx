"use client";

import { cn } from "@/lib/cn";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";

type Ctx = { close: () => void };

const DropdownContext = createContext<Ctx | null>(null);

export function DropdownMenu({
  trigger,
  children,
  align = "end",
}: {
  trigger: ReactNode;
  children: ReactNode;
  align?: "start" | "end";
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const close = useCallback(() => setOpen(false), []);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <DropdownContext.Provider value={{ close }}>
      <div className="relative" ref={ref}>
        <div
          onClick={(e) => {
            e.stopPropagation();
            setOpen((o) => !o);
          }}
        >
          {trigger}
        </div>
        {open ? (
          <div
            role="menu"
            className={cn(
              "absolute z-[250] mt-1 min-w-[168px] overflow-hidden rounded-xl border border-slate-200/90 bg-white/95 py-1 shadow-xl shadow-slate-900/10 transition-[opacity,transform] duration-200 animate-[ds-modal-in_0.2s_ease-out]",
              "dark:border-slate-600 dark:bg-slate-900/95 dark:shadow-black/50",
              align === "end" ? "right-0" : "left-0",
            )}
          >
            {children}
          </div>
        ) : null}
      </div>
    </DropdownContext.Provider>
  );
}

export function DropdownMenuItem({
  children,
  onClick,
  destructive,
  disabled,
}: {
  children: ReactNode;
  onClick?: () => void;
  destructive?: boolean;
  disabled?: boolean;
}) {
  const ctx = useContext(DropdownContext);
  return (
    <button
      type="button"
      role="menuitem"
      disabled={disabled}
      className={cn(
        "flex w-full items-center gap-2 px-3 py-2.5 text-left text-sm font-semibold transition-colors duration-150",
        destructive
          ? "text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950/40"
          : "text-foreground hover:bg-primary/10",
        disabled && "pointer-events-none opacity-40",
      )}
      onClick={() => {
        if (disabled) return;
        onClick?.();
        ctx?.close();
      }}
    >
      {children}
    </button>
  );
}
