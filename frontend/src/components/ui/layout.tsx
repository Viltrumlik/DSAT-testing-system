import type { HTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/cn";

/** Page-width wrapper with responsive gutters. */
export function Container({
  size = "lg",
  className,
  ...rest
}: HTMLAttributes<HTMLDivElement> & { size?: "sm" | "md" | "lg" | "xl" | "full" }) {
  const max = {
    sm: "max-w-3xl",
    md: "max-w-5xl",
    lg: "max-w-6xl",
    xl: "max-w-7xl",
    full: "max-w-none",
  }[size];
  return <div className={cn("mx-auto w-full px-4 sm:px-6 lg:px-8", max, className)} {...rest} />;
}

/** Flex stack helper. */
export function Stack({
  direction = "col",
  gap = 4,
  align,
  justify,
  wrap,
  className,
  ...rest
}: HTMLAttributes<HTMLDivElement> & {
  direction?: "row" | "col";
  gap?: 1 | 2 | 3 | 4 | 5 | 6 | 8;
  align?: "start" | "center" | "end" | "stretch";
  justify?: "start" | "center" | "end" | "between";
  wrap?: boolean;
}) {
  const gapClass = { 1: "gap-1", 2: "gap-2", 3: "gap-3", 4: "gap-4", 5: "gap-5", 6: "gap-6", 8: "gap-8" }[gap];
  return (
    <div
      className={cn(
        "flex",
        direction === "col" ? "flex-col" : "flex-row",
        gapClass,
        align && `items-${align}`,
        justify && `justify-${justify}`,
        wrap && "flex-wrap",
        className,
      )}
      {...rest}
    />
  );
}

/** Section heading block: eyebrow + title + description + actions. */
export function PageHeading({
  eyebrow,
  title,
  description,
  actions,
  className,
}: {
  eyebrow?: ReactNode;
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between", className)}>
      <div className="min-w-0">
        {eyebrow ? <p className="ds-overline mb-1.5 text-primary">{eyebrow}</p> : null}
        <h1 className="ds-h1">{title}</h1>
        {description ? <p className="ds-lead mt-1.5 max-w-2xl">{description}</p> : null}
      </div>
      {actions ? <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  );
}
