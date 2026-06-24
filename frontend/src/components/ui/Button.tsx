import { forwardRef } from "react";
import type { ButtonHTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/cn";
import { Spinner } from "./Spinner";

export type ButtonVariant =
  | "primary"
  | "secondary"
  | "outline"
  | "ghost"
  | "subtle"
  | "danger";
export type ButtonSize = "sm" | "md" | "lg";

export type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  leftIcon?: ReactNode;
  rightIcon?: ReactNode;
  fullWidth?: boolean;
};

const base =
  "ds-ring inline-flex items-center justify-center font-semibold whitespace-nowrap select-none " +
  "transition-[background-color,border-color,color,box-shadow,transform] duration-150 ease-[var(--ds-ease-premium)] " +
  "active:scale-[0.98] disabled:pointer-events-none disabled:opacity-50";

const variants: Record<ButtonVariant, string> = {
  primary:
    "bg-primary text-primary-foreground shadow-[0_1px_2px_rgba(67,56,202,0.35)] hover:bg-primary-hover",
  secondary:
    "border border-border bg-card text-foreground shadow-card hover:border-border-strong hover:bg-surface-2",
  outline:
    "border border-primary/30 bg-transparent text-primary hover:bg-primary-soft",
  ghost: "bg-transparent text-muted-foreground hover:bg-surface-2 hover:text-foreground",
  subtle: "bg-primary-soft text-primary hover:bg-primary/15",
  danger: "bg-danger text-white shadow-[0_1px_2px_rgba(220,38,38,0.3)] hover:brightness-95",
};

const sizes: Record<ButtonSize, string> = {
  sm: "h-9 gap-1.5 rounded-lg px-3 text-[13px]",
  md: "h-11 gap-2 rounded-xl px-4 text-sm",
  lg: "h-12 gap-2 rounded-xl px-6 text-[15px]",
};

const iconSize: Record<ButtonSize, string> = {
  sm: "[&_svg]:h-4 [&_svg]:w-4",
  md: "[&_svg]:h-[18px] [&_svg]:w-[18px]",
  lg: "[&_svg]:h-5 [&_svg]:w-5",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    variant = "primary",
    size = "md",
    loading = false,
    leftIcon,
    rightIcon,
    fullWidth,
    className,
    disabled,
    type,
    children,
    ...rest
  },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type ?? "button"}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={cn(
        base,
        variants[variant],
        sizes[size],
        iconSize[size],
        fullWidth && "w-full",
        className,
      )}
      {...rest}
    >
      {loading ? (
        <Spinner className={size === "sm" ? "h-4 w-4" : "h-[18px] w-[18px]"} />
      ) : (
        leftIcon
      )}
      {children}
      {!loading && rightIcon}
    </button>
  );
});
