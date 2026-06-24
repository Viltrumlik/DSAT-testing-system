"use client";
import { FloatingPanel } from "./FloatingPanel";

interface ReferenceSheetProps {
  onClose: () => void;
}

/**
 * Official-style SAT Math reference sheet: the standard 2D figures + formulas
 * row, the 3D solids + volume row, and the three constant notes — laid out to
 * mirror the printed College Board reference. Content only; no exam coupling.
 *
 * Figures are inline SVG so they render crisply at any zoom and need no assets.
 */
const STROKE = "#0f172a";

function Figure({ children, formula }: { children: React.ReactNode; formula: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-end gap-1.5">
      <svg viewBox="0 0 120 90" className="h-[78px] w-[110px]" fill="none" stroke={STROKE} strokeWidth={1.5}>
        {children}
      </svg>
      <div className="text-center font-[Georgia] text-[13px] leading-tight text-slate-900">{formula}</div>
    </div>
  );
}

const Sup = ({ children }: { children: React.ReactNode }) => <sup className="text-[0.7em]">{children}</sup>;
const Frac = ({ n, d }: { n: string; d: string }) => (
  <span className="inline-flex flex-col items-center align-middle text-[0.75em] leading-none">
    <span className="border-b border-slate-900 px-0.5">{n}</span>
    <span className="px-0.5">{d}</span>
  </span>
);

export function ReferenceSheet({ onClose }: ReferenceSheetProps) {
  return (
    <FloatingPanel title="Reference Sheet" onClose={onClose} initial={{ x: 160, y: 90, w: 720, h: 560 }} minW={460} minH={380}>
      <div className="p-5">
        <div className="mb-2 inline-block rounded bg-slate-900 px-2 py-0.5 text-[10px] font-bold uppercase tracking-widest text-white">
          Reference
        </div>

        {/* ── Row 1: plane figures ─────────────────────────────────────────── */}
        <div className="grid grid-cols-3 gap-x-4 gap-y-5 sm:grid-cols-6">
          {/* Circle */}
          <Figure formula={<><div>A = πr<Sup>2</Sup></div><div>C = 2πr</div></>}>
            <circle cx="48" cy="42" r="32" />
            <circle cx="48" cy="42" r="2" fill={STROKE} />
            <line x1="48" y1="42" x2="80" y2="42" />
            <text x="60" y="38" fontSize="11" stroke="none" fill={STROKE} fontStyle="italic">r</text>
          </Figure>
          {/* Rectangle */}
          <Figure formula={<>A = ℓw</>}>
            <rect x="22" y="26" width="76" height="40" />
            <text x="56" y="20" fontSize="11" stroke="none" fill={STROKE} fontStyle="italic">ℓ</text>
            <text x="104" y="50" fontSize="11" stroke="none" fill={STROKE} fontStyle="italic">w</text>
          </Figure>
          {/* Triangle */}
          <Figure formula={<>A = <Frac n="1" d="2" /> bh</>}>
            <path d="M20 70 L70 70 L52 24 Z" />
            <line x1="52" y1="24" x2="52" y2="70" strokeDasharray="3 3" />
            <text x="55" y="50" fontSize="11" stroke="none" fill={STROKE} fontStyle="italic">h</text>
            <text x="42" y="84" fontSize="11" stroke="none" fill={STROKE} fontStyle="italic">b</text>
          </Figure>
          {/* Right triangle / Pythagorean */}
          <Figure formula={<>c<Sup>2</Sup> = a<Sup>2</Sup> + b<Sup>2</Sup></>}>
            <path d="M22 70 L92 70 L22 28 Z" />
            <path d="M30 70 L30 62 L22 62" />
            <text x="6" y="52" fontSize="11" stroke="none" fill={STROKE} fontStyle="italic">b</text>
            <text x="60" y="44" fontSize="11" stroke="none" fill={STROKE} fontStyle="italic">c</text>
            <text x="52" y="84" fontSize="11" stroke="none" fill={STROKE} fontStyle="italic">a</text>
          </Figure>
          {/* 30-60-90 */}
          <Figure formula={<>30°-60°-90°</>}>
            <path d="M18 70 L96 70 L96 30 Z" />
            <text x="40" y="84" fontSize="10" stroke="none" fill={STROKE} fontStyle="italic">x√3</text>
            <text x="100" y="54" fontSize="10" stroke="none" fill={STROKE} fontStyle="italic">x</text>
            <text x="48" y="44" fontSize="10" stroke="none" fill={STROKE} fontStyle="italic">2x</text>
            <text x="26" y="66" fontSize="8" stroke="none" fill={STROKE}>30°</text>
            <text x="80" y="42" fontSize="8" stroke="none" fill={STROKE}>60°</text>
          </Figure>
          {/* 45-45-90 */}
          <Figure formula={<>45°-45°-90°</>}>
            <path d="M22 70 L86 70 L86 28 Z" />
            <text x="46" y="84" fontSize="10" stroke="none" fill={STROKE} fontStyle="italic">s</text>
            <text x="90" y="54" fontSize="10" stroke="none" fill={STROKE} fontStyle="italic">s</text>
            <text x="44" y="44" fontSize="10" stroke="none" fill={STROKE} fontStyle="italic">s√2</text>
            <text x="30" y="66" fontSize="8" stroke="none" fill={STROKE}>45°</text>
          </Figure>
        </div>

        <p className="my-3 text-center text-[11px] font-semibold text-slate-500">Special Right Triangles</p>

        {/* ── Row 2: solids ────────────────────────────────────────────────── */}
        <div className="grid grid-cols-3 gap-x-4 gap-y-5 sm:grid-cols-5">
          {/* Rectangular solid */}
          <Figure formula={<>V = ℓwh</>}>
            <path d="M20 40 L60 40 L60 74 L20 74 Z" />
            <path d="M20 40 L34 26 L74 26 L60 40" />
            <path d="M60 40 L74 26 L74 60 L60 74" />
            <text x="36" y="86" fontSize="10" stroke="none" fill={STROKE} fontStyle="italic">ℓ</text>
            <text x="14" y="60" fontSize="10" stroke="none" fill={STROKE} fontStyle="italic">h</text>
            <text x="70" y="20" fontSize="10" stroke="none" fill={STROKE} fontStyle="italic">w</text>
          </Figure>
          {/* Cylinder */}
          <Figure formula={<>V = πr<Sup>2</Sup>h</>}>
            <ellipse cx="48" cy="24" rx="26" ry="8" />
            <path d="M22 24 L22 66" />
            <path d="M74 24 L74 66" />
            <path d="M22 66 A26 8 0 0 0 74 66" />
            <line x1="48" y1="24" x2="74" y2="24" strokeDasharray="3 3" />
            <text x="58" y="20" fontSize="10" stroke="none" fill={STROKE} fontStyle="italic">r</text>
            <text x="78" y="48" fontSize="10" stroke="none" fill={STROKE} fontStyle="italic">h</text>
          </Figure>
          {/* Sphere */}
          <Figure formula={<>V = <Frac n="4" d="3" />πr<Sup>3</Sup></>}>
            <circle cx="48" cy="44" r="28" />
            <ellipse cx="48" cy="44" rx="28" ry="9" strokeDasharray="3 3" />
            <line x1="48" y1="44" x2="74" y2="40" />
            <text x="58" y="38" fontSize="10" stroke="none" fill={STROKE} fontStyle="italic">r</text>
          </Figure>
          {/* Cone */}
          <Figure formula={<>V = <Frac n="1" d="3" />πr<Sup>2</Sup>h</>}>
            <path d="M48 18 L22 64 L74 64 Z" />
            <ellipse cx="48" cy="64" rx="26" ry="8" />
            <line x1="48" y1="18" x2="48" y2="64" strokeDasharray="3 3" />
            <line x1="48" y1="64" x2="74" y2="64" />
            <text x="38" y="46" fontSize="10" stroke="none" fill={STROKE} fontStyle="italic">h</text>
            <text x="60" y="62" fontSize="10" stroke="none" fill={STROKE} fontStyle="italic">r</text>
          </Figure>
          {/* Pyramid */}
          <Figure formula={<>V = <Frac n="1" d="3" />ℓwh</>}>
            <path d="M48 16 L20 60 L60 72 L88 50 Z" />
            <path d="M48 16 L60 72" strokeDasharray="3 3" />
            <path d="M48 16 L20 60 M48 16 L88 50" />
            <text x="40" y="44" fontSize="10" stroke="none" fill={STROKE} fontStyle="italic">h</text>
            <text x="34" y="72" fontSize="10" stroke="none" fill={STROKE} fontStyle="italic">ℓ</text>
            <text x="74" y="66" fontSize="10" stroke="none" fill={STROKE} fontStyle="italic">w</text>
          </Figure>
        </div>

        {/* ── Constant notes ───────────────────────────────────────────────── */}
        <div className="mt-4 space-y-1 border-t border-slate-200 pt-3 text-[12px] text-slate-600">
          <p>The number of degrees of arc in a circle is 360.</p>
          <p>The number of radians of arc in a circle is 2π.</p>
          <p>The sum of the measures in degrees of the angles of a triangle is 180.</p>
        </div>
      </div>
    </FloatingPanel>
  );
}
