"use client";
import { useEffect } from "react";
import { renderMath } from "@/lib/mathRender";

/**
 * Keeps KaTeX math rendered as the DOM changes (question switches, answer edits,
 * zoom). A debounced MutationObserver replaces the fragile dependency-array
 * approach the legacy runner used.
 */
export function useMathRendering(enabled: boolean, resetKey: unknown): void {
  useEffect(() => {
    if (!enabled) return;
    let debounce: ReturnType<typeof setTimeout> | null = null;
    const schedule = () => {
      if (debounce) clearTimeout(debounce);
      debounce = setTimeout(() => renderMath({ root: document.body }), 40);
    };

    renderMath({ root: document.body });
    const initial = setTimeout(() => renderMath({ root: document.body }), 80);

    const observer = new MutationObserver(schedule);
    observer.observe(document.body, { childList: true, subtree: true, characterData: true });
    const onReady = () => schedule();
    window.addEventListener("katex:ready", onReady);

    return () => {
      if (debounce) clearTimeout(debounce);
      clearTimeout(initial);
      observer.disconnect();
      window.removeEventListener("katex:ready", onReady);
    };
  }, [enabled, resetKey]);
}
