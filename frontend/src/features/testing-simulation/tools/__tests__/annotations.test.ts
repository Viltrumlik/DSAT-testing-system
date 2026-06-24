import { beforeEach, describe, expect, it } from "vitest";
import {
  addHighlight,
  addUnderline,
  annotationsAt,
  applyAnnotations,
  clearAnnotations,
  computeSegments,
  mergeAnnotations,
  rangeToOffsets,
  removeRange,
  type Annotation,
} from "../highlight/annotations";

const H = (start: number, end: number, color: Annotation["color"] = "yellow"): Annotation => ({ start, end, kind: "highlight", color });
const U = (start: number, end: number, underline: Annotation["underline"] = "solid"): Annotation => ({ start, end, kind: "underline", underline });

describe("merge rules", () => {
  it("merges same-colour overlapping highlights", () => {
    expect(mergeAnnotations([H(0, 5), H(4, 8)])).toEqual([H(0, 8)]);
  });
  it("keeps different-colour highlights separate", () => {
    const out = mergeAnnotations([H(0, 5, "yellow"), H(5, 9, "blue")]);
    expect(out).toHaveLength(2);
  });
  it("keeps a highlight and an underline as independent layers", () => {
    const out = mergeAnnotations([H(0, 6), U(0, 6)]);
    expect(out.filter((a) => a.kind === "highlight")).toHaveLength(1);
    expect(out.filter((a) => a.kind === "underline")).toHaveLength(1);
  });
});

describe("addHighlight — new colour wins in the overlap", () => {
  it("recolours only the overlapping part, splitting the old highlight", () => {
    const out = addHighlight([H(0, 10, "yellow")], { start: 3, end: 6 }, "pink");
    const sorted = out.filter((a) => a.kind === "highlight").sort((a, b) => a.start - b.start);
    expect(sorted).toEqual([H(0, 3, "yellow"), H(3, 6, "pink"), H(6, 10, "yellow")]);
  });
  it("does NOT disturb an underline under the same region", () => {
    const out = addHighlight([U(0, 10)], { start: 2, end: 5 }, "blue");
    expect(out.filter((a) => a.kind === "underline")).toEqual([U(0, 10)]);
    expect(out.filter((a) => a.kind === "highlight")).toEqual([H(2, 5, "blue")]);
  });
});

describe("addUnderline — independent of highlights", () => {
  it("underline over a highlight keeps both layers", () => {
    const out = addUnderline([H(0, 10, "yellow")], { start: 2, end: 6 }, "dashed");
    expect(out.filter((a) => a.kind === "highlight")).toEqual([H(0, 10, "yellow")]);
    expect(out.filter((a) => a.kind === "underline")).toEqual([U(2, 6, "dashed")]);
  });
  it("new underline style wins in the overlap", () => {
    const out = addUnderline([U(0, 10, "solid")], { start: 4, end: 7 }, "dotted");
    const sorted = out.filter((a) => a.kind === "underline").sort((a, b) => a.start - b.start);
    expect(sorted).toEqual([U(0, 4, "solid"), U(4, 7, "dotted"), U(7, 10, "solid")]);
  });
});

describe("removeRange — deletes from both layers", () => {
  it("removes the overlapping portion of highlight and underline", () => {
    const out = removeRange([H(0, 10), U(0, 10)], { start: 3, end: 6 });
    expect(out.filter((a) => a.kind === "highlight")).toEqual([H(0, 3), H(6, 10)]);
    expect(out.filter((a) => a.kind === "underline")).toEqual([U(0, 3), U(6, 10)]);
  });
});

describe("computeSegments — flattens layers for painting", () => {
  it("a highlight+underline overlap yields a combined segment", () => {
    const segs = computeSegments([H(0, 10, "blue"), U(4, 8, "dotted")]);
    // 0-4 blue, 4-8 blue+dotted, 8-10 blue
    expect(segs).toEqual([
      { start: 0, end: 4, color: "blue", underline: undefined },
      { start: 4, end: 8, color: "blue", underline: "dotted" },
      { start: 8, end: 10, color: "blue", underline: undefined },
    ]);
  });
});

describe("annotationsAt", () => {
  it("returns both layers covering an offset", () => {
    const at = annotationsAt([H(0, 10), U(2, 6)], 4);
    expect(at).toHaveLength(2);
  });
});

describe("applyAnnotations / clearAnnotations (jsdom)", () => {
  let container: HTMLElement;
  beforeEach(() => {
    container = document.createElement("div");
    container.innerHTML = "The quick brown fox";
    document.body.appendChild(container);
  });

  it("wraps a highlight range in a coloured mark", () => {
    applyAnnotations(container, [H(4, 9, "blue")]); // "quick"
    const marks = container.querySelectorAll("mark.ts-annot");
    expect(marks).toHaveLength(1);
    expect(marks[0].textContent).toBe("quick");
    expect((marks[0] as HTMLElement).dataset.color).toBe("blue");
    expect(container.textContent).toBe("The quick brown fox");
  });

  it("paints a highlight+underline region as one mark with both styles", () => {
    applyAnnotations(container, [H(4, 9, "yellow"), U(4, 9, "dashed")]);
    const mark = container.querySelector("mark.ts-annot") as HTMLElement;
    expect(mark.dataset.color).toBe("yellow");
    expect(mark.dataset.underline).toBe("dashed");
    expect(mark.style.textDecorationStyle).toBe("dashed");
  });

  it("clearAnnotations restores the original text", () => {
    applyAnnotations(container, [H(4, 9)]);
    clearAnnotations(container);
    expect(container.querySelectorAll("mark.ts-annot")).toHaveLength(0);
    expect(container.textContent).toBe("The quick brown fox");
  });

  it("re-applying is idempotent (no nested marks)", () => {
    applyAnnotations(container, [H(4, 9)]);
    applyAnnotations(container, [H(4, 9)]);
    expect(container.querySelectorAll("mark.ts-annot")).toHaveLength(1);
  });

  it("rangeToOffsets round-trips a DOM Range", () => {
    const textNode = container.firstChild as Text;
    const range = document.createRange();
    range.setStart(textNode, 4);
    range.setEnd(textNode, 9);
    expect(rangeToOffsets(container, range)).toEqual({ start: 4, end: 9 });
  });
});
