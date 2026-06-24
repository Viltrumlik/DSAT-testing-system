/** Resolve a possibly-relative media path against the API origin. */
export function resolveImageUrl(path: string | null | undefined): string | undefined {
  if (!path) return undefined;
  if (path.startsWith("http")) return path;
  const base = process.env.NEXT_PUBLIC_API_URL?.replace("/api", "") || "";
  return `${base}${path}`;
}
