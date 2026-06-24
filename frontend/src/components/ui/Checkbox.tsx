import { forwardRef } from "react";
import type { InputHTMLAttributes } from "react";
import { Check } from "lucide-react";
import { cn } from "@/lib/cn";

export type CheckboxProps = Omit<InputHTMLAttributes<HTMLInputElement>, "type" | "size"> & {
  label?: string;
};

export const Checkbox = forwardRef<HTMLInputElement, CheckboxProps>(function Checkbox(
  { label, className, id, ...rest },
  ref,
) {
  const inner = (
    <span className="relative inline-flex h-[18px] w-[18px] shrink-0 items-center justify-center">
      <input
        ref={ref}
        id={id}
        type="checkbox"
        className={cn(
          "peer ds-ring h-[18px] w-[18px] cursor-pointer appearance-none rounded-[6px] border border-border bg-background transition-colors",
          "checked:border-primary checked:bg-primary",
          "disabled:cursor-not-allowed disabled:opacity-60",
          className,
        )}
        {...rest}
      />
      <Check
        className="pointer-events-none absolute h-3 w-3 text-primary-foreground opacity-0 peer-checked:opacity-100"
        strokeWidth={3.5}
      />
    </span>
  );

  if (!label) return inner;
  return (
    <label htmlFor={id} className="inline-flex cursor-pointer items-center gap-2.5 text-sm text-foreground">
      {inner}
      <span>{label}</span>
    </label>
  );
});
