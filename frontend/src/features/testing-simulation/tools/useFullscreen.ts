"use client";
import { useCallback, useEffect, useState } from "react";

/**
 * Thin, cross-browser wrapper over the Fullscreen API. Self-contained — no exam
 * coupling. Tracks state via the change event (standard + webkit) so the UI
 * stays in sync even when the user exits with Esc.
 *
 * Robustness (regression fix): `enter()` never re-requests while already
 * fullscreen and `exit()` never exits when not fullscreen, so transient
 * `fullscreenchange` churn can't trigger redundant requests / flicker. Webkit
 * fallbacks ensure Safari can actually enter (and thus dismiss the warning).
 */
type FsDoc = Document & {
  webkitFullscreenElement?: Element | null;
  webkitExitFullscreen?: () => Promise<void> | void;
};
type FsEl = HTMLElement & { webkitRequestFullscreen?: () => Promise<void> | void };

function fullscreenElement(): Element | null {
  if (typeof document === "undefined") return null;
  return document.fullscreenElement ?? (document as FsDoc).webkitFullscreenElement ?? null;
}

export function useFullscreen(target?: () => Element | null) {
  const [isFullscreen, setIsFullscreen] = useState(false);

  useEffect(() => {
    const onChange = () => setIsFullscreen(Boolean(fullscreenElement()));
    document.addEventListener("fullscreenchange", onChange);
    document.addEventListener("webkitfullscreenchange", onChange as EventListener);
    onChange(); // sync initial state
    return () => {
      document.removeEventListener("fullscreenchange", onChange);
      document.removeEventListener("webkitfullscreenchange", onChange as EventListener);
    };
  }, []);

  const enter = useCallback(async () => {
    if (fullscreenElement()) return; // already fullscreen — never double-request
    const el = (target?.() ?? document.documentElement) as FsEl;
    const req = el.requestFullscreen ?? el.webkitRequestFullscreen;
    if (!req) return;
    try {
      await req.call(el);
    } catch {
      /* user denied / not permitted right now */
    }
  }, [target]);

  const exit = useCallback(async () => {
    if (!fullscreenElement()) return;
    const d = document as FsDoc;
    const ex = document.exitFullscreen ?? d.webkitExitFullscreen;
    if (!ex) return;
    try {
      await ex.call(document);
    } catch {
      /* ignore */
    }
  }, []);

  const toggle = useCallback(() => {
    if (fullscreenElement()) void exit();
    else void enter();
  }, [enter, exit]);

  const supported =
    typeof document !== "undefined" &&
    Boolean(document.documentElement.requestFullscreen || (document.documentElement as FsEl).webkitRequestFullscreen);

  return { isFullscreen, enter, exit, toggle, supported };
}
