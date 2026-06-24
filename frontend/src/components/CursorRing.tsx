"use client";

import { useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";

function isCursorRingDisabled(pathname: string | null): boolean {
  if (!pathname) return false;
  return pathname.startsWith("/exam") || pathname.startsWith("/profile") || pathname.startsWith("/builder") || pathname.startsWith("/assessments/assign");
}

/**
 * Small blue ring that follows the pointer (light UI). Disabled on exam and admin.
 */
export default function CursorRing() {
  const pathname = usePathname();
  const disabled = isCursorRingDisabled(pathname);

  const [pos, setPos] = useState({ x: -100, y: -100 });
  const [visible, setVisible] = useState(false);
  const raf = useRef<number | null>(null);
  const pending = useRef({ x: 0, y: 0 });

  useEffect(() => {
    if (disabled) {
      setVisible(false);
      return;
    }

    const onMove = (e: MouseEvent) => {
      pending.current = { x: e.clientX, y: e.clientY };
      if (raf.current == null) {
        raf.current = requestAnimationFrame(() => {
          raf.current = null;
          setPos({ x: pending.current.x, y: pending.current.y });
        });
      }
      const edgePad = 20;
      const isNearEdge =
        e.clientX < edgePad ||
        e.clientY < edgePad ||
        e.clientX > window.innerWidth - edgePad ||
        e.clientY > window.innerHeight - edgePad;
      setVisible(!isNearEdge);
    };
    const onLeave = () => setVisible(false);
    window.addEventListener("mousemove", onMove, { passive: true });
    document.documentElement.addEventListener("mouseleave", onLeave);
    return () => {
      window.removeEventListener("mousemove", onMove);
      document.documentElement.removeEventListener("mouseleave", onLeave);
      if (raf.current != null) cancelAnimationFrame(raf.current);
    };
  }, [disabled]);

  if (disabled || !visible) return null;

  return (
    <div
      className="pointer-events-none fixed z-[10000] w-8 h-8 rounded-full border-2 border-blue-500 ring-2 ring-blue-400/30"
      style={{
        left: pos.x,
        top: pos.y,
        transform: "translate(-50%, -50%)",
      }}
      aria-hidden
    />
  );
}
