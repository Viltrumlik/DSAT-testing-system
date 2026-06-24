import type { HTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/cn";

export type CardVariant = "default" | "soft" | "outlined" | "interactive";

const variants: Record<CardVariant, string> = {
  default: "border border-border bg-card shadow-card",
  soft: "border border-transparent bg-surface-2",
  outlined: "border border-border bg-transparent",
  interactive:
    "border border-border bg-card shadow-card transition-[border-color,box-shadow,transform] duration-150 hover:border-border-strong hover:shadow-pop cursor-pointer",
};

export function Card({
  variant = "default",
  className,
  children,
  ...rest
}: HTMLAttributes<HTMLDivElement> & { variant?: CardVariant }) {
  return (
    <div className={cn("rounded-2xl", variants[variant], className)} {...rest}>
      {children}
    </div>
  );
}

export function CardHeader({
  className,
  children,
  ...rest
}: HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn("flex items-start justify-between gap-3 px-5 pt-5", className)} {...rest}>
      {children}
    </div>
  );
}

export function CardTitle({
  className,
  children,
  ...rest
}: HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h3 className={cn("ds-h4", className)} {...rest}>
      {children}
    </h3>
  );
}

export function CardDescription({
  className,
  children,
  ...rest
}: HTMLAttributes<HTMLParagraphElement>) {
  return (
    <p className={cn("mt-0.5 text-sm text-muted-foreground", className)} {...rest}>
      {children}
    </p>
  );
}

export function CardContent({
  className,
  children,
  ...rest
}: HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn("p-5", className)} {...rest}>
      {children}
    </div>
  );
}

export function CardFooter({
  className,
  children,
  ...rest
}: HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn("flex items-center gap-3 border-t border-border px-5 py-4", className)} {...rest}>
      {children}
    </div>
  );
}

/** Convenience: titled section header inside a card body. */
export function CardSectionTitle({ children }: { children: ReactNode }) {
  return <p className="ds-overline mb-3">{children}</p>;
}
