import { cn } from "@/lib/cn";

export type SkeletonProps = {
  className?: string;
  /** shape preset */
  variant?: "rect" | "text" | "circle";
};

export function Skeleton({ className, variant = "rect" }: SkeletonProps) {
  return (
    <span
      aria-hidden
      className={cn(
        "ds-skeleton block",
        variant === "circle" && "rounded-full",
        variant === "text" && "h-3.5 rounded-md",
        variant === "rect" && "rounded-lg",
        className,
      )}
    />
  );
}

/** Multi-line text placeholder. */
export function SkeletonText({ lines = 3, className }: { lines?: number; className?: string }) {
  return (
    <span className={cn("flex flex-col gap-2", className)}>
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton
          key={i}
          variant="text"
          className={i === lines - 1 ? "w-2/3" : "w-full"}
        />
      ))}
    </span>
  );
}
