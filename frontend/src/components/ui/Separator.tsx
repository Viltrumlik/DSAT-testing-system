import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

export function Separator({
  orientation = "horizontal",
  label,
  className,
}: {
  orientation?: "horizontal" | "vertical";
  label?: ReactNode;
  className?: string;
}) {
  if (orientation === "vertical") {
    return <span role="separator" aria-orientation="vertical" className={cn("inline-block w-px self-stretch bg-border", className)} />;
  }
  if (label) {
    return (
      <div className={cn("flex items-center gap-3", className)} role="separator">
        <span className="h-px flex-1 bg-border" />
        <span className="ds-overline">{label}</span>
        <span className="h-px flex-1 bg-border" />
      </div>
    );
  }
  return <hr className={cn("border-0 border-t border-border", className)} />;
}
