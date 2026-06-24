/**
 * Bluebook-style text annotations over a container's visible text.
 *
 * Annotations are stored as character-offset ranges (NOT serialized HTML) so
 * they survive React re-renders without clobbering the rendered question, and
 * never touch the exam engine.
 *
 * ── DATA MODEL ────────────────────────────────────────────────────────────────
 *   Annotation = { start, end, kind }
 *     kind "highlight" → carries `color`     (yellow | blue | pink)
 *     kind "underline" → carries `underline` (solid | dashed | dotted)
 *
 * Highlights and underlines are TWO INDEPENDENT LAYERS: a span of text can be
 * both highlighted and underlined at once. Within a single layer, ranges never
 * overlap (adds subtract first), so at any character there is at most one
 * highlight and at most one underline.
 *
 * ── MERGE / OVERLAP RULES ─────────────────────────────────────────────────────
 *   • highlight over highlight → in the overlap, the NEW colour replaces the old;
 *     the old highlight's non-overlapping parts keep their colour.
 *   • underline over underline → same: new style wins in the overlap.
 *   • underline over highlight (and vice-versa) → independent layers, both kept
 *     (the text shows the background colour AND the underline together).
 *   • adjacent/overlapping ranges of the same kind AND same value → merged.
 *   • delete over a range → removes that range from BOTH layers (splitting any
 *     annotation that only partially overlaps).
 */

export type HighlightColor = "yellow" | "blue" | "pink";
export type UnderlineStyle = "solid" | "dashed" | "dotted";
export type AnnotationKind = "highlight" | "underline";

export interface Annotation {
  start: number;
  end: number;
  kind: AnnotationKind;
  color?: HighlightColor; // when kind === "highlight"
  underline?: UnderlineStyle; // when kind === "underline"
}

export interface OffsetRange {
  start: number;
  end: number;
}

const MARK = "ts-annot";

const HL_BG: Record<HighlightColor, string> = {
  yellow: "#fde047",
  blue: "#93c5fd",
  pink: "#f9a8d4",
};
const UNDERLINE_COLOR = "#0f172a";

// ── Range algebra ─────────────────────────────────────────────────────────────

/** Remove [hole.start, hole.end) from every annotation, splitting as needed and
 *  preserving each annotation's kind/colour/underline. */
function subtract(anns: Annotation[], hole: OffsetRange): Annotation[] {
  const out: Annotation[] = [];
  for (const a of anns) {
    if (hole.end <= a.start || hole.start >= a.end) {
      out.push(a);
      continue;
    }
    if (a.start < hole.start) out.push({ ...a, end: hole.start });
    if (hole.end < a.end) out.push({ ...a, start: hole.end });
  }
  return out.filter((a) => a.end > a.start);
}

function sameStyle(a: Annotation, b: Annotation): boolean {
  return a.kind === b.kind && a.color === b.color && a.underline === b.underline;
}

/** Merge adjacent/overlapping annotations that share kind + value. */
export function mergeAnnotations(anns: Annotation[]): Annotation[] {
  const sorted = [...anns]
    .filter((a) => a.end > a.start)
    .sort((x, y) => (x.kind === y.kind ? x.start - y.start || x.end - y.end : x.kind < y.kind ? -1 : 1));
  const out: Annotation[] = [];
  for (const a of sorted) {
    const last = out[out.length - 1];
    if (last && sameStyle(last, a) && a.start <= last.end) last.end = Math.max(last.end, a.end);
    else out.push({ ...a });
  }
  return out;
}

/** Add a highlight: subtract overlap from the highlight layer only, then add. */
export function addHighlight(anns: Annotation[], range: OffsetRange, color: HighlightColor): Annotation[] {
  if (range.end <= range.start) return anns;
  const highlights = subtract(anns.filter((a) => a.kind === "highlight"), range);
  const underlines = anns.filter((a) => a.kind === "underline");
  return mergeAnnotations([...highlights, ...underlines, { ...range, kind: "highlight", color }]);
}

/** Add an underline: subtract overlap from the underline layer only, then add. */
export function addUnderline(anns: Annotation[], range: OffsetRange, underline: UnderlineStyle): Annotation[] {
  if (range.end <= range.start) return anns;
  const underlines = subtract(anns.filter((a) => a.kind === "underline"), range);
  const highlights = anns.filter((a) => a.kind === "highlight");
  return mergeAnnotations([...highlights, ...underlines, { ...range, kind: "underline", underline }]);
}

/** Remove a range from BOTH layers (delete). */
export function removeRange(anns: Annotation[], range: OffsetRange): Annotation[] {
  return mergeAnnotations(subtract(anns, range));
}

/** Annotations covering a character offset (across both layers). */
export function annotationsAt(anns: Annotation[], offset: number): Annotation[] {
  return anns.filter((a) => a.start <= offset && offset < a.end);
}

/** The smallest range covering a set of annotations (union extent). */
export function boundingRange(anns: Annotation[]): OffsetRange | null {
  if (!anns.length) return null;
  return { start: Math.min(...anns.map((a) => a.start)), end: Math.max(...anns.map((a) => a.end)) };
}

// ── Painting (segment-based, overlap-safe) ────────────────────────────────────

export interface Segment {
  start: number;
  end: number;
  color?: HighlightColor;
  underline?: UnderlineStyle;
}

/** Flatten the two layers into non-overlapping painted segments. For every
 *  boundary span, the segment carries the highlight colour and/or underline
 *  style covering it. Adjacent identical segments are merged. */
export function computeSegments(anns: Annotation[]): Segment[] {
  const bounds = new Set<number>();
  for (const a of anns) {
    bounds.add(a.start);
    bounds.add(a.end);
  }
  const points = [...bounds].sort((x, y) => x - y);
  const raw: Segment[] = [];
  for (let i = 0; i < points.length - 1; i++) {
    const s = points[i];
    const e = points[i + 1];
    if (e <= s) continue;
    const hl = anns.find((a) => a.kind === "highlight" && a.start <= s && a.end >= e);
    const ul = anns.find((a) => a.kind === "underline" && a.start <= s && a.end >= e);
    if (hl || ul) raw.push({ start: s, end: e, color: hl?.color, underline: ul?.underline });
  }
  const out: Segment[] = [];
  for (const seg of raw) {
    const last = out[out.length - 1];
    if (last && last.end === seg.start && last.color === seg.color && last.underline === seg.underline) last.end = seg.end;
    else out.push({ ...seg });
  }
  return out;
}

function textNodesWithOffsets(container: HTMLElement): Array<{ node: Text; start: number }> {
  const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
  const list: Array<{ node: Text; start: number }> = [];
  let acc = 0;
  let n = walker.nextNode();
  while (n) {
    const text = n as Text;
    list.push({ node: text, start: acc });
    acc += text.length;
    n = walker.nextNode();
  }
  return list;
}

function paintMark(mark: HTMLElement, seg: Segment): void {
  if (seg.color) {
    mark.style.backgroundColor = HL_BG[seg.color];
    mark.dataset.color = seg.color;
  } else {
    mark.style.backgroundColor = "transparent";
  }
  if (seg.underline) {
    mark.style.textDecorationLine = "underline";
    mark.style.textDecorationStyle = seg.underline;
    mark.style.textDecorationColor = UNDERLINE_COLOR;
    mark.style.textDecorationThickness = "2px";
    mark.style.textUnderlineOffset = "2px";
    mark.dataset.underline = seg.underline;
  }
  mark.style.color = "inherit";
}

/** Character offsets of a selection Range relative to the container's text. */
export function rangeToOffsets(container: HTMLElement, range: Range): OffsetRange | null {
  const nodes = textNodesWithOffsets(container);
  let start = -1;
  let end = -1;
  for (const { node, start: base } of nodes) {
    if (node === range.startContainer) start = base + range.startOffset;
    if (node === range.endContainer) end = base + range.endOffset;
  }
  if (start < 0 || end < 0 || end <= start) return null;
  return { start, end };
}

/** Remove all annotation marks, restoring the original text/structure. */
export function clearAnnotations(container: HTMLElement): void {
  container.querySelectorAll(`mark.${MARK}`).forEach((mark) => {
    const parent = mark.parentNode;
    if (!parent) return;
    while (mark.firstChild) parent.insertBefore(mark.firstChild, mark);
    parent.removeChild(mark);
  });
  container.normalize();
}

/** Paint annotations by wrapping each painted segment's text in a <mark>. */
export function applyAnnotations(container: HTMLElement, anns: Annotation[]): void {
  clearAnnotations(container);
  const segs = computeSegments(anns);
  if (segs.length === 0) return;

  const nodes = textNodesWithOffsets(container);
  const spans: Array<{ node: Text; localStart: number; localEnd: number; seg: Segment }> = [];
  for (const { node, start: base } of nodes) {
    const nodeEnd = base + node.length;
    for (const seg of segs) {
      const s = Math.max(seg.start, base);
      const e = Math.min(seg.end, nodeEnd);
      if (e > s) spans.push({ node, localStart: s - base, localEnd: e - base, seg });
    }
  }
  // Wrap in reverse document order so splitting earlier nodes never invalidates
  // references we haven't used yet.
  for (let i = spans.length - 1; i >= 0; i--) {
    const { node, localStart, localEnd, seg } = spans[i];
    try {
      const range = document.createRange();
      range.setStart(node, localStart);
      range.setEnd(node, localEnd);
      const mark = document.createElement("mark");
      mark.className = MARK;
      paintMark(mark, seg);
      range.surroundContents(mark);
    } catch {
      /* skip a span that can't be cleanly wrapped */
    }
  }
}

/** If a click landed on an annotation mark, return it. */
export function markFromEvent(target: EventTarget | null): HTMLElement | null {
  let el = target as HTMLElement | null;
  while (el) {
    if (el.tagName === "MARK" && el.classList.contains(MARK)) return el;
    el = el.parentElement;
  }
  return null;
}

/** Character offsets covered by a specific mark element. */
export function offsetsOfMark(container: HTMLElement, mark: HTMLElement): OffsetRange | null {
  const range = document.createRange();
  range.selectNodeContents(mark);
  return rangeToOffsets(container, range);
}
