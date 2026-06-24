"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import { CheckCircle2, Info, AlertTriangle, AlertCircle, X } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/cn";

export type ToastTone = "info" | "success" | "warning" | "danger";

type ToastInput = {
  title: string;
  description?: string;
  tone?: ToastTone;
  duration?: number;
};
type ToastRecord = ToastInput & { id: number; tone: ToastTone };

const ToastContext = createContext<((t: ToastInput) => void) | null>(null);

const toneIcon: Record<ToastTone, LucideIcon> = {
  info: Info,
  success: CheckCircle2,
  warning: AlertTriangle,
  danger: AlertCircle,
};
const toneAccent: Record<ToastTone, string> = {
  info: "text-info",
  success: "text-success",
  warning: "text-warning",
  danger: "text-danger",
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastRecord[]>([]);
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const remove = useCallback((id: number) => {
    setToasts((cur) => cur.filter((t) => t.id !== id));
  }, []);

  const push = useCallback(
    (t: ToastInput) => {
      const id = Date.now() + Math.random();
      const rec: ToastRecord = { id, tone: "info", ...t };
      setToasts((cur) => [...cur, rec]);
      window.setTimeout(() => remove(id), t.duration ?? 4200);
    },
    [remove],
  );

  return (
    <ToastContext.Provider value={push}>
      {children}
      {mounted
        ? createPortal(
            <div className="pointer-events-none fixed bottom-4 right-4 z-[400] flex w-[min(100vw-2rem,360px)] flex-col gap-2">
              {toasts.map((t) => {
                const Icon = toneIcon[t.tone];
                return (
                  <div
                    key={t.id}
                    role="status"
                    className="ds-anim-pop pointer-events-auto flex items-start gap-3 rounded-xl border border-border bg-card p-3.5 shadow-modal"
                  >
                    <Icon className={cn("mt-0.5 h-5 w-5 shrink-0", toneAccent[t.tone])} />
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-semibold text-foreground">{t.title}</p>
                      {t.description ? (
                        <p className="mt-0.5 text-[13px] text-muted-foreground">{t.description}</p>
                      ) : null}
                    </div>
                    <button
                      type="button"
                      onClick={() => remove(t.id)}
                      aria-label="Dismiss"
                      className="ds-ring -m-1 rounded-md p-1 text-muted-foreground transition-colors hover:text-foreground"
                    >
                      <X className="h-4 w-4" />
                    </button>
                  </div>
                );
              })}
            </div>,
            document.body,
          )
        : null}
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    // No-op fallback so callers don't crash outside a provider.
    return (_t: ToastInput) => {
      if (process.env.NODE_ENV !== "production") {
        // eslint-disable-next-line no-console
        console.warn("useToast called outside <ToastProvider>");
      }
    };
  }
  return ctx;
}
