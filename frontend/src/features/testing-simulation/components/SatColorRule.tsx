"use client";

/**
 * SatColorRule — the Bluebook-style multi-colour dashed rule (red / amber /
 * green / navy) used at the top and bottom edges of the testing surface and at
 * the section boundary inside the answer pane. Decorative only.
 */
export function SatColorRule({ className = "" }: { className?: string }) {
  return (
    <div
      aria-hidden
      className={`h-[3px] w-full shrink-0 ${className}`}
      style={{
        background:
          "repeating-linear-gradient(to right, #b91c1c 0, #b91c1c 48px, transparent 48px, transparent 54px, #ca8a04 54px, #ca8a04 102px, transparent 102px, transparent 108px, #15803d 108px, #15803d 156px, transparent 156px, transparent 162px, #0f172a 162px, #0f172a 210px, transparent 210px, transparent 216px)",
      }}
    />
  );
}
