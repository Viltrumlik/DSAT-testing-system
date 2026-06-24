"use client";
import { useMemo, useState } from "react";
import { evaluate, tryEvaluate } from "./expression";

const KEYS: Array<{ label: string; insert?: string; act?: "clear" | "back" }> = [
  { label: "sin", insert: "sin(" }, { label: "cos", insert: "cos(" }, { label: "tan", insert: "tan(" }, { label: "^", insert: "^" }, { label: "√", insert: "sqrt(" },
  { label: "ln", insert: "ln(" }, { label: "log", insert: "log(" }, { label: "(", insert: "(" }, { label: ")", insert: ")" }, { label: "!", insert: "!" },
  { label: "7", insert: "7" }, { label: "8", insert: "8" }, { label: "9", insert: "9" }, { label: "÷", insert: "/" }, { label: "π", insert: "pi" },
  { label: "4", insert: "4" }, { label: "5", insert: "5" }, { label: "6", insert: "6" }, { label: "×", insert: "*" }, { label: "e", insert: "e" },
  { label: "1", insert: "1" }, { label: "2", insert: "2" }, { label: "3", insert: "3" }, { label: "−", insert: "-" }, { label: "%", insert: "%" },
  { label: "0", insert: "0" }, { label: ".", insert: "." }, { label: "C", act: "clear" }, { label: "⌫", act: "back" }, { label: "+", insert: "+" },
];

/** Built-in scientific calculator body (no panel chrome). Offline fallback for Desmos. */
export function ScientificCalculator() {
  const [expr, setExpr] = useState("");
  const [degrees, setDegrees] = useState(true);
  const preview = useMemo(() => (expr ? tryEvaluate(expr, { degrees }) : ""), [expr, degrees]);

  const press = (k: (typeof KEYS)[number]) => {
    if (k.act === "clear") return setExpr("");
    if (k.act === "back") return setExpr((e) => e.slice(0, -1));
    if (k.insert != null) return setExpr((e) => e + k.insert);
  };
  const equals = () => {
    try {
      setExpr(String(Number.parseFloat(evaluate(expr, { degrees }).toPrecision(12))));
    } catch {
      /* leave input; preview shows "Error" */
    }
  };

  return (
    <div className="flex h-full flex-col p-3">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-[11px] font-bold uppercase tracking-widest text-slate-400">Scientific</span>
        <button type="button" onClick={() => setDegrees((d) => !d)} className="rounded-md border border-slate-300 px-2 py-0.5 text-xs font-bold text-slate-600 hover:bg-slate-50">
          {degrees ? "DEG" : "RAD"}
        </button>
      </div>
      <div className="mb-3 rounded-lg border border-slate-200 bg-slate-50 p-3 text-right">
        <div className="min-h-[20px] break-all font-mono text-sm text-slate-500">{expr || "0"}</div>
        <div className="min-h-[28px] break-all font-mono text-2xl font-bold text-slate-900">{preview || "0"}</div>
      </div>
      <div className="grid flex-1 grid-cols-5 gap-1.5">
        {KEYS.map((k) => (
          <button
            key={k.label}
            type="button"
            onClick={() => press(k)}
            className={`rounded-md text-sm font-semibold transition-colors ${
              k.act === "clear" ? "bg-red-50 text-red-600 hover:bg-red-100" : /[0-9.]/.test(k.label) ? "bg-white text-slate-900 ring-1 ring-slate-200 hover:bg-slate-50" : "bg-slate-100 text-slate-700 hover:bg-slate-200"
            }`}
          >
            {k.label}
          </button>
        ))}
        <button type="button" onClick={equals} className="col-span-5 mt-1 rounded-md bg-blue-600 py-2 text-sm font-bold text-white hover:bg-blue-700">
          =
        </button>
      </div>
    </div>
  );
}
