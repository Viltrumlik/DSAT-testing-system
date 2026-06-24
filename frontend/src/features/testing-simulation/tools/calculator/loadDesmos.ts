/**
 * Lazy, single-flight loader for the Desmos Graphing Calculator API (the real
 * SAT calculator). Returns the global `Desmos` factory, or `null` if the script
 * can't load (offline / CSP) so the UI can fall back to the built-in calculator.
 *
 * Override the key with NEXT_PUBLIC_DESMOS_API_KEY. The default is Desmos's
 * public demo key.
 */
export interface DesmosInstance {
  destroy(): void;
  resize(): void;
}
export interface DesmosFactory {
  GraphingCalculator(el: HTMLElement, options?: Record<string, unknown>): DesmosInstance;
  /** Same Desmos `calculator.js` bundle also ships the scientific calculator. */
  ScientificCalculator?(el: HTMLElement, options?: Record<string, unknown>): DesmosInstance;
}

declare global {
  var Desmos: DesmosFactory | undefined;
}

const DEFAULT_KEY = "dcb31709b452b1cf9dc26972add0fda6";
let pending: Promise<DesmosFactory | null> | null = null;

export function loadDesmos(): Promise<DesmosFactory | null> {
  if (typeof window === "undefined") return Promise.resolve(null);
  if (globalThis.Desmos) return Promise.resolve(globalThis.Desmos);
  if (pending) return pending;

  const key = process.env.NEXT_PUBLIC_DESMOS_API_KEY || DEFAULT_KEY;
  pending = new Promise((resolve) => {
    const script = document.createElement("script");
    script.src = `https://www.desmos.com/api/v1.11/calculator.js?apiKey=${key}`;
    script.async = true;
    script.onload = () => resolve(globalThis.Desmos ?? null);
    script.onerror = () => resolve(null);
    document.head.appendChild(script);
  });
  return pending;
}
