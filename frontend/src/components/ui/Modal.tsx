"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import type { ReactNode } from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/cn";

export type ModalProps = {
  open: boolean;
  onClose: () => void;
  title?: ReactNode;
  description?: ReactNode;
  children?: ReactNode;
  footer?: ReactNode;
  size?: "sm" | "md" | "lg" | "xl";
  /** Hide the default close (×) button */
  hideClose?: boolean;
};

const sizeClass = {
  sm: "max-w-sm",
  md: "max-w-lg",
  lg: "max-w-2xl",
  xl: "max-w-4xl",
};

export function Modal({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  size = "md",
  hideClose,
}: ModalProps) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [open, onClose]);

  if (!mounted || !open) return null;

  return createPortal(
    <div className="fixed inset-0 z-[200] flex items-center justify-center p-4">
      <div
        className="ds-anim-fade absolute inset-0 bg-[var(--overlay-scrim)] backdrop-blur-[2px]"
        onClick={onClose}
        aria-hidden
      />
      <div
        role="dialog"
        aria-modal="true"
        className={cn(
          "ds-anim-pop relative z-10 flex w-full flex-col overflow-hidden rounded-2xl border border-border bg-card shadow-modal",
          sizeClass[size],
        )}
      >
        {title || !hideClose ? (
          <div className="flex items-start justify-between gap-4 border-b border-border px-5 py-4">
            <div className="min-w-0">
              {title ? <h2 className="ds-h3 truncate">{title}</h2> : null}
              {description ? (
                <p className="mt-0.5 text-sm text-muted-foreground">{description}</p>
              ) : null}
            </div>
            {!hideClose ? (
              <button
                type="button"
                onClick={onClose}
                aria-label="Close"
                className="ds-ring -m-1.5 shrink-0 rounded-lg p-1.5 text-muted-foreground transition-colors hover:bg-surface-2 hover:text-foreground"
              >
                <X className="h-5 w-5" />
              </button>
            ) : null}
          </div>
        ) : null}
        {children ? <div className="max-h-[70vh] overflow-y-auto px-5 py-5">{children}</div> : null}
        {footer ? (
          <div className="flex items-center justify-end gap-3 border-t border-border bg-surface-1 px-5 py-4">
            {footer}
          </div>
        ) : null}
      </div>
    </div>,
    document.body,
  );
}
