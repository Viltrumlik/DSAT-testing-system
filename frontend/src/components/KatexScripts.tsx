"use client";

/**
 * KatexScripts — loads KaTeX CDN scripts and fires a katex:ready event
 * when the auto-render extension finishes loading.
 *
 * Must be a Client Component because Next.js forbids passing function props
 * (onLoad) to <Script> from Server Components.
 *
 * MathText listens for the katex:ready event to re-render nodes that mounted
 * before KaTeX finished loading (strategy="afterInteractive" race condition).
 */

import Script from "next/script";

export function KatexScripts() {
  return (
    <>
      <Script
        src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js"
        strategy="afterInteractive"
      />
      <Script
        src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/contrib/auto-render.min.js"
        strategy="afterInteractive"
        onLoad={() => {
          window.dispatchEvent(new CustomEvent("katex:ready"));
        }}
      />
    </>
  );
}
