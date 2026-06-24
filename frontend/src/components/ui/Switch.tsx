"use client";

import { cn } from "@/lib/cn";

export type SwitchProps = {
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  disabled?: boolean;
  label?: string;
  id?: string;
  className?: string;
};

export function Switch({
  checked,
  onCheckedChange,
  disabled,
  label,
  id,
  className,
}: SwitchProps) {
  const control = (
    <button
      type="button"
      role="switch"
      id={id}
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onCheckedChange(!checked)}
      className={cn(
        "ds-ring relative inline-flex h-6 w-11 shrink-0 items-center rounded-full border border-transparent transition-colors duration-200",
        checked ? "bg-primary" : "bg-surface-3",
        disabled && "cursor-not-allowed opacity-60",
        className,
      )}
    >
      <span
        className={cn(
          "inline-block h-5 w-5 transform rounded-full bg-white shadow-sm transition-transform duration-200",
          checked ? "translate-x-[22px]" : "translate-x-[2px]",
        )}
      />
    </button>
  );

  if (!label) return control;
  return (
    <label htmlFor={id} className="inline-flex cursor-pointer items-center gap-3 text-sm text-foreground">
      {control}
      <span>{label}</span>
    </label>
  );
}
