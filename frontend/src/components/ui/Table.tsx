import type { HTMLAttributes, TdHTMLAttributes, ThHTMLAttributes } from "react";
import { cn } from "@/lib/cn";

export function Table({
  className,
  containerClassName,
  ...rest
}: HTMLAttributes<HTMLTableElement> & { containerClassName?: string }) {
  return (
    <div className={cn("w-full overflow-x-auto rounded-2xl border border-border bg-card", containerClassName)}>
      <table className={cn("w-full border-collapse text-sm", className)} {...rest} />
    </div>
  );
}

export function TableHead({ className, ...rest }: HTMLAttributes<HTMLTableSectionElement>) {
  return <thead className={cn("bg-surface-2", className)} {...rest} />;
}

export function TableBody({ className, ...rest }: HTMLAttributes<HTMLTableSectionElement>) {
  return <tbody className={cn("divide-y divide-border", className)} {...rest} />;
}

export function TableRow({
  className,
  interactive,
  ...rest
}: HTMLAttributes<HTMLTableRowElement> & { interactive?: boolean }) {
  return (
    <tr
      className={cn(interactive && "cursor-pointer transition-colors hover:bg-surface-2", className)}
      {...rest}
    />
  );
}

export function TableHeaderCell({ className, ...rest }: ThHTMLAttributes<HTMLTableCellElement>) {
  return (
    <th
      className={cn(
        "whitespace-nowrap px-4 py-3 text-left text-[11px] font-bold uppercase tracking-wider text-label-foreground",
        className,
      )}
      {...rest}
    />
  );
}

export function TableCell({ className, ...rest }: TdHTMLAttributes<HTMLTableCellElement>) {
  return <td className={cn("px-4 py-3 align-middle text-foreground", className)} {...rest} />;
}
