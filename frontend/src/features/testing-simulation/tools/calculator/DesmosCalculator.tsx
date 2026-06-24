"use client";
import { useEffect, useRef, useState } from "react";
import { Maximize2, Minimize2 } from "lucide-react";
import { FloatingPanel } from "../FloatingPanel";
import { ScientificCalculator } from "./ScientificCalculator";
import { loadDesmos, type DesmosInstance } from "./loadDesmos";

interface DesmosCalculatorProps {
  onClose: () => void;
  /** Enlarged window (and the runner reserves more space for it). */
  enlarged: boolean;
  onToggleEnlarge: () => void;
}

type Mode = "graphing" | "scientific";

/**
 * The real Desmos calculator (as used on the digital SAT) in a draggable floating
 * panel. Two tabs — Graphing and Scientific — both from the same Desmos bundle;
 * falls back to the built-in scientific calculator if the script can't load
 * (offline / CSP). An enlarge button grows the window. UI-only; no exam coupling.
 */
export function DesmosCalculator({ onClose, enlarged, onToggleEnlarge }: DesmosCalculatorProps) {
  const [mode, setMode] = useState<Mode>("graphing");
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const mountRef = useRef<HTMLDivElement>(null);
  const instanceRef = useRef<DesmosInstance | null>(null);

  // (Re)mount the Desmos instance whenever the tab changes.
  useEffect(() => {
    let cancelled = false;
    setStatus("loading");
    loadDesmos().then((factory) => {
      if (cancelled || !mountRef.current) return;
      const create = mode === "scientific" ? factory?.ScientificCalculator : factory?.GraphingCalculator;
      if (!factory || typeof create !== "function") {
        setStatus("error");
        return;
      }
      instanceRef.current =
        mode === "scientific"
          ? create(mountRef.current, {})
          : create(mountRef.current, { expressions: true, settingsMenu: false, zoomButtons: true, border: false });
      setStatus("ready");
    });
    return () => {
      cancelled = true;
      instanceRef.current?.destroy();
      instanceRef.current = null;
    };
  }, [mode]);

  // Tabs live in the dark title bar; stopPropagation keeps a tap from starting a
  // window drag.
  const tab = (m: Mode, label: string) => (
    <button
      type="button"
      onMouseDown={(e) => e.stopPropagation()}
      onClick={() => setMode(m)}
      aria-pressed={mode === m}
      className={`rounded-md px-3 py-1 text-xs font-bold transition-colors ${
        mode === m ? "bg-white text-slate-900" : "text-slate-300 hover:text-white"
      }`}
    >
      {label}
    </button>
  );

  return (
    <FloatingPanel
      title="Calculator"
      onClose={onClose}
      dark
      initial={{ x: 16, y: 80, w: enlarged ? 720 : 460, h: enlarged ? 700 : 560 }}
      minW={360}
      minH={420}
      headerLeft={
        <div className="flex items-center gap-1">
          {tab("graphing", "Graphing")}
          {tab("scientific", "Scientific")}
        </div>
      }
      headerExtra={
        <button
          type="button"
          onMouseDown={(e) => e.stopPropagation()}
          onClick={onToggleEnlarge}
          aria-label={enlarged ? "Shrink calculator" : "Enlarge calculator"}
          title={enlarged ? "Shrink" : "Enlarge"}
          className="rounded p-0.5 text-slate-300 hover:bg-white/10 hover:text-white"
        >
          {enlarged ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
        </button>
      }
    >
      <div className="relative h-full w-full">
        {status === "error" ? (
          <ScientificCalculator />
        ) : (
          <>
            <div ref={mountRef} className="h-full w-full" />
            {status === "loading" && (
              <div className="absolute inset-0 flex items-center justify-center bg-white/70">
                <div className="h-8 w-8 animate-spin rounded-full border-4 border-slate-200 border-t-blue-600" />
              </div>
            )}
          </>
        )}
      </div>
    </FloatingPanel>
  );
}
