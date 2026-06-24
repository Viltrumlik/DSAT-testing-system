"use client";

import { useState } from "react";
import { cn } from "@/lib/cn";

export type AvatarProps = {
  src?: string | null;
  name?: string;
  size?: number;
  className?: string;
};

function initials(name?: string): string {
  if (!name) return "?";
  const parts = name.trim().split(/\s+/).slice(0, 2);
  return parts.map((p) => p[0]?.toUpperCase() ?? "").join("") || "?";
}

export function Avatar({ src, name, size = 40, className }: AvatarProps) {
  const [failed, setFailed] = useState(false);
  const showImg = src && !failed;
  return (
    <span
      className={cn(
        "relative inline-flex shrink-0 items-center justify-center overflow-hidden rounded-full bg-primary-soft font-semibold text-primary",
        className,
      )}
      style={{ width: size, height: size, fontSize: Math.max(11, size * 0.36) }}
    >
      {showImg ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={src ?? undefined}
          alt=""
          className="absolute inset-0 h-full w-full object-cover"
          onError={() => setFailed(true)}
        />
      ) : (
        initials(name)
      )}
    </span>
  );
}
