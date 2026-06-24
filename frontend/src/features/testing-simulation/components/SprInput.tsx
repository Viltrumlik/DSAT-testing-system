"use client";

interface SprInputProps {
  value: string;
  onChange: (value: string) => void;
}

/** Renders an "a/b" answer as a stacked fraction; otherwise plain text. */
function RecordedAnswer({ text }: { text: string }) {
  if (!text) return <span>—</span>;
  if (text.includes("/")) {
    const [num, den] = text.split("/");
    return (
      <span className="inline-flex flex-col items-center justify-center font-black leading-none">
        <span className="border-b-[2.5px] border-slate-900 px-[2px] pb-[1px]">{num}</span>
        <span className="px-[2px] pt-[1px]">{den}</span>
      </span>
    );
  }
  return <span>{text}</span>;
}

/** Student-produced response input (math grid-ins). Accepts digits, -, ., /. */
export function SprInput({ value, onChange }: SprInputProps) {
  return (
    <div className="mt-6">
      <p className="mb-2 text-[11px] font-bold uppercase tracking-widest text-slate-400">Your Answer</p>
      <input
        type="text"
        inputMode="text"
        placeholder="Enter your answer"
        maxLength={5}
        value={value}
        onChange={(e) => {
          const next = e.target.value.slice(0, 5);
          if (/^[-0-9./]*$/.test(next)) onChange(next);
        }}
        className="w-full max-w-xs rounded-lg border-2 border-slate-300 p-3 px-4 text-center text-xl font-bold tracking-widest text-slate-900 shadow-sm outline-2 outline-offset-1 outline-blue-600 transition-all hover:border-slate-400 focus:border-blue-600 focus:outline"
      />
      <div className="mt-3 flex max-w-xs items-center gap-2">
        <span className="text-[11px] font-bold uppercase tracking-widest text-slate-400">Recorded:</span>
        <span className="flex min-h-[30px] min-w-[30px] items-center justify-center rounded border border-slate-200 bg-slate-100 px-2 py-0.5 text-sm font-black text-slate-900">
          <RecordedAnswer text={value} />
        </span>
      </div>
    </div>
  );
}
