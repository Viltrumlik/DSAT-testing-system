import { cn } from "@/lib/cn";

type Size = "sm" | "md" | "lg";

const SIZE: Record<Size, string> = {
  sm: "h-5 w-5 border-2",
  md: "h-8 w-8 border-[3px]",
  lg: "h-10 w-10 border-4",
};

/**
 * StudioSpinner — canonical loading indicator for the SAT Content Studio.
 *
 * Usage:
 *   <StudioSpinner />               // md, centered inline
 *   <StudioSpinner size="lg" center />  // large, centered in a flex container
 */
export function StudioSpinner({
  size = "md",
  center = false,
  className,
}: {
  size?: Size;
  center?: boolean;
  className?: string;
}) {
  const spinner = (
    <div
      aria-label="Loading"
      role="status"
      className={cn(
        "animate-spin rounded-full border-primary border-t-transparent",
        SIZE[size],
        className,
      )}
    />
  );

  if (center) {
    return (
      <div className="flex flex-1 items-center justify-center py-16">
        {spinner}
      </div>
    );
  }

  return spinner;
}
