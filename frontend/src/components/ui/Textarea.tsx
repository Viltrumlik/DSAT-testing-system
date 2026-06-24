import { forwardRef } from "react";
import type { TextareaHTMLAttributes } from "react";
import { cn } from "@/lib/cn";

export type TextareaProps = TextareaHTMLAttributes<HTMLTextAreaElement> & {
  invalid?: boolean;
};

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(function Textarea(
  { invalid, className, rows = 4, ...rest },
  ref,
) {
  return (
    <textarea
      ref={ref}
      rows={rows}
      aria-invalid={invalid || undefined}
      className={cn(
        "ds-ring w-full rounded-xl border bg-background px-3.5 py-2.5 text-sm text-foreground shadow-card transition-colors duration-150",
        "placeholder:text-label-foreground resize-y",
        "focus-visible:border-primary focus-visible:shadow-[0_0_0_3px_var(--primary-soft)]",
        "disabled:cursor-not-allowed disabled:opacity-60",
        invalid
          ? "border-danger focus-visible:border-danger focus-visible:shadow-[0_0_0_3px_var(--danger-soft)]"
          : "border-border",
        className,
      )}
      {...rest}
    />
  );
});
