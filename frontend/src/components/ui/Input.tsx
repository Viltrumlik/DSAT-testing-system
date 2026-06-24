import { forwardRef } from "react";
import type { InputHTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/cn";

export type InputProps = InputHTMLAttributes<HTMLInputElement> & {
  leftIcon?: ReactNode;
  rightSlot?: ReactNode;
  invalid?: boolean;
  inputSize?: "sm" | "md" | "lg";
};

const sizes = {
  sm: "h-9 text-[13px]",
  md: "h-11 text-sm",
  lg: "h-12 text-[15px]",
};

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { leftIcon, rightSlot, invalid, inputSize = "md", className, ...rest },
  ref,
) {
  return (
    <div className="relative w-full">
      {leftIcon ? (
        <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-label-foreground [&_svg]:h-[18px] [&_svg]:w-[18px]">
          {leftIcon}
        </span>
      ) : null}
      <input
        ref={ref}
        aria-invalid={invalid || undefined}
        className={cn(
          "ds-ring w-full rounded-xl border bg-background text-foreground shadow-card transition-colors duration-150",
          "placeholder:text-label-foreground",
          "focus-visible:border-primary focus-visible:shadow-[0_0_0_3px_var(--primary-soft)]",
          "disabled:cursor-not-allowed disabled:opacity-60",
          sizes[inputSize],
          leftIcon ? "pl-10" : "pl-3.5",
          rightSlot ? "pr-10" : "pr-3.5",
          invalid
            ? "border-danger focus-visible:border-danger focus-visible:shadow-[0_0_0_3px_var(--danger-soft)]"
            : "border-border",
          className,
        )}
        {...rest}
      />
      {rightSlot ? (
        <span className="absolute right-3 top-1/2 -translate-y-1/2 text-label-foreground">
          {rightSlot}
        </span>
      ) : null}
    </div>
  );
});
