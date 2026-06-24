"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { cn } from "@/lib/cn";

export type Toast = { id: string; message: string; tone?: "neutral" | "success" | "error" };

const ToastCtx = createContext<{ push: (t: Omit<Toast, "id">) => void } | null>(null);

function uid() {
  return Math.random().toString(36).slice(2) + Date.now().toString(36);
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const push = useCallback((t: Omit<Toast, "id">) => {
    const id = uid();
    const toast: Toast = { id, tone: t.tone || "neutral", message: t.message };
    setToasts((prev) => [toast, ...prev].slice(0, 3));
    window.setTimeout(() => {
      setToasts((prev) => prev.filter((x) => x.id !== id));
    }, 3200);
  }, []);

  useEffect(() => {
    const onEvt = (e: Event) => {
      const d = (e as CustomEvent<{ tone?: Toast["tone"]; message?: string }>).detail;
      if (!d?.message) return;
      push({ tone: d.tone || "neutral", message: String(d.message) });
    };
    window.addEventListener("mastersat-toast", onEvt as EventListener);
    return () => window.removeEventListener("mastersat-toast", onEvt as EventListener);
  }, [push]);

  const value = useMemo(() => ({ push }), [push]);

  return (
    <ToastCtx.Provider value={value}>
      {children}
      <div className="fixed right-3 top-3 z-[200] flex w-[min(92vw,420px)] flex-col gap-2 md:right-5 md:top-5">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={cn(
              "rounded-2xl border border-border bg-card px-4 py-3 shadow-lg",
              t.tone === "success" && "border-primary/20 bg-primary/5",
              t.tone === "error" && "border-red-500/20 bg-red-500/5",
            )}
          >
            <p className="text-sm font-extrabold text-foreground">{t.tone === "error" ? "Error" : "Notice"}</p>
            <p className="mt-1 text-sm text-muted-foreground">{t.message}</p>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastCtx);
  if (!ctx) throw new Error("useToast must be used within ToastProvider");
  return ctx;
}

