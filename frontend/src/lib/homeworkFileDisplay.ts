/** Best-effort display name from a stored file URL (API often returns URLs only). */
export function fileNameFromUrl(url: string): string {
  try {
    const u = new URL(url, typeof window !== "undefined" ? window.location.origin : "https://localhost");
    const path = u.pathname;
    const seg = path.split("/").filter(Boolean).pop() || "";
    const decoded = decodeURIComponent(seg.replace(/\+/g, " "));
    return decoded.trim() || "File";
  } catch {
    const q = url.split("?")[0] || url;
    const seg = q.split("/").filter(Boolean).pop() || "";
    try {
      return decodeURIComponent(seg) || "File";
    } catch {
      return seg || "File";
    }
  }
}

export function isImageMimeOrName(mime: string | undefined, fileName: string): boolean {
  const m = (mime || "").toLowerCase();
  if (m.startsWith("image/")) return true;
  const fn = fileName.toLowerCase();
  return /\.(png|jpe?g|gif|webp|svg|bmp|heic|avif)$/i.test(fn);
}

export function isPdfMimeOrName(mime: string | undefined, fileName: string): boolean {
  const m = (mime || "").toLowerCase();
  if (m.includes("pdf")) return true;
  return fileName.toLowerCase().endsWith(".pdf");
}
