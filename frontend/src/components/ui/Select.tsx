import { forwardRef } from "react";
import type { SelectHTMLAttributes } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/cn";

export type SelectProps = SelectHTMLAttributes<HTMLSelectElement> & {
  invalid?: boolean;
  selectSize?: "sm" | "md" | "lg";
};

const sizes = {
  sm: "h-9 text-[13px]",
  md: "h-11 text-sm",
  lg: "h-12 text-[15px]",
};

export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { invalid, selectSize = "md", className, children, ...rest },
  ref,
) {
  return (
    <div className="relative w-full">
      <select
        ref={ref}
        aria-invalid={invalid || undefined}
        className={cn(
          "ds-ring w-full appearance-none rounded-xl border bg-background pl-3.5 pr-10 text-foreground shadow-card transition-colors duration-150",
          "focus-visible:border-primary focus-visible:shadow-[0_0_0_3px_var(--primary-soft)]",
          "disabled:cursor-not-allowed disabled:opacity-60",
          sizes[selectSize],
          invalid ? "border-danger" : "border-border",
          className,
        )}
        {...rest}
      >
        {children}
      </select>
      <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-label-foreground" />
    </div>
  );
});
