"use client";
import { PanelLeftClose, PanelLeftOpen } from "lucide-react";

interface StudentProducedResponseGuideProps {
  expanded: boolean;
  onToggle: () => void;
}

const BULLETS: string[] = [
  "If you find more than one correct answer, enter only one answer.",
  "You can enter up to 5 characters for a positive answer and up to 6 characters (including the negative sign) for a negative answer.",
  "If your answer is a fraction that doesn’t fit in the provided space, enter the decimal equivalent.",
  "If your answer is a decimal that doesn’t fit in the provided space, enter it by truncating or rounding at the fourth digit.",
  "If your answer is a mixed number (such as 3½), enter it as an improper fraction (7/2) or its decimal equivalent (3.5).",
  "Don’t enter symbols such as a percent sign, comma, or dollar sign.",
];

const EXAMPLES: Array<{ answer: string; acceptable: string[]; unacceptable: string[] }> = [
  { answer: "3.5", acceptable: ["3.5", "3.50", "7/2"], unacceptable: ["31/2", "3 1/2"] },
  { answer: "2/3", acceptable: ["2/3", ".6666", ".6667", "0.666", "0.667"], unacceptable: ["0.66", ".66", "0.67", ".67"] },
  { answer: "-1/3", acceptable: ["-1/3", "-.3333", "-0.333"], unacceptable: ["-.33", "-0.33"] },
];

/**
 * StudentProducedResponseGuide — the official SAT "Student-Produced Response
 * Directions" panel (bullets + Acceptable/Unacceptable examples table).
 *
 * Reusable + self-contained: it owns only its own presentation. The runner
 * decides WHEN to show it (SPR questions only) and controls the column width;
 * `expanded`/`onToggle` are lifted so the collapse state persists across SPR
 * questions. When collapsed it renders a thin rail with a toggle so the question
 * gets more width.
 */
export function StudentProducedResponseGuide({ expanded, onToggle }: StudentProducedResponseGuideProps) {
  if (!expanded) {
    return (
      <div className="flex h-full w-full flex-col items-center border-r border-slate-200 bg-slate-50 py-3">
        <button
          type="button"
          onClick={onToggle}
          aria-label="Show directions"
          aria-expanded={false}
          title="Show directions"
          className="rounded-lg border border-slate-300 p-1.5 text-slate-600 hover:border-slate-400 hover:text-slate-900"
        >
          <PanelLeftOpen className="h-4 w-4" />
        </button>
        <span className="mt-3 rotate-180 text-[11px] font-bold uppercase tracking-widest text-slate-500 [writing-mode:vertical-rl]">
          Directions
        </span>
      </div>
    );
  }

  return (
    <div className="flex h-full w-full flex-col border-r border-slate-200 bg-white">
      <div className="flex shrink-0 items-start justify-between gap-3 px-6 pt-6">
        <h2 className="text-lg font-bold tracking-tight text-slate-900">Student-Produced Response Directions</h2>
        <button
          type="button"
          onClick={onToggle}
          aria-label="Collapse directions"
          aria-expanded
          title="Collapse directions"
          className="mt-0.5 shrink-0 rounded-lg border border-slate-300 p-1.5 text-slate-600 hover:border-slate-400 hover:text-slate-900"
        >
          <PanelLeftClose className="h-4 w-4" />
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-6 pb-6">
        <ul className="mt-4 space-y-2.5 text-[15px] leading-snug text-slate-800">
          {BULLETS.map((b, i) => (
            <li key={i} className="flex gap-2">
              <span aria-hidden className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-slate-400" />
              <span>{b}</span>
            </li>
          ))}
        </ul>

        <h3 className="mb-2 mt-6 text-base font-bold text-slate-900">Examples</h3>
        <table className="w-full border-collapse overflow-hidden rounded-lg border border-slate-200 text-[13px]">
          <thead>
            <tr className="bg-slate-50 text-left align-top font-bold text-slate-700">
              <th className="border-b border-slate-200 px-3 py-2">Answer</th>
              <th className="border-b border-slate-200 px-3 py-2">Acceptable ways to enter answer</th>
              <th className="border-b border-slate-200 px-3 py-2">Unacceptable: will NOT receive credit</th>
            </tr>
          </thead>
          <tbody className="align-top text-slate-800">
            {EXAMPLES.map((row) => (
              <tr key={row.answer} className="border-b border-slate-100 last:border-0">
                <td className="px-3 py-3 font-semibold">{row.answer}</td>
                <td className="px-3 py-3">
                  <div className="space-y-1">
                    {row.acceptable.map((a) => (
                      <div key={a}>{a}</div>
                    ))}
                  </div>
                </td>
                <td className="px-3 py-3">
                  <div className="space-y-1">
                    {row.unacceptable.map((u) => (
                      <div key={u}>{u}</div>
                    ))}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
