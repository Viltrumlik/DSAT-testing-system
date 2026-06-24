/* eslint-disable react-hooks/globals -- test harness intentionally exposes hook state via module vars */
import { useMemo, useState, act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useAnnotator } from "../highlight/useAnnotator";

let latest: ReturnType<typeof useAnnotator>;
function Harness() {
  latest = useAnnotator({
    getContainers: () => [{ key: "passage", el: document.getElementById("ts-passage") }],
    attemptId: 1,
    questionId: 1,
    active: true,
  });
  return null;
}

// Mimics SafeHtml + PassagePane: text via dangerouslySetInnerHTML, parent re-renders.
let bump: () => void;
function App() {
  const [tick, setTick] = useState(0);
  bump = () => setTick((t) => t + 1);
  useAnnotator({
    getContainers: () => [{ key: "passage", el: document.getElementById("ts-passage") }],
    attemptId: 2,
    questionId: 2,
    active: true,
  });
  const html = "The quick brown fox jumps";
  const safe = useMemo(() => `${html}`, [html]);
  return (
    <div data-tick={tick}>
      <div id="ts-passage" dangerouslySetInnerHTML={{ __html: safe }} />
    </div>
  );
}

function mockSelectionOver(textNode: Text, start: number, end: number) {
  const range = document.createRange();
  range.setStart(textNode, start);
  range.setEnd(textNode, end);
  range.getBoundingClientRect = () =>
    ({ left: 100, top: 200, width: 50, height: 16, right: 150, bottom: 216, x: 100, y: 200, toJSON: () => ({}) }) as DOMRect;
  vi.spyOn(window, "getSelection").mockReturnValue({
    isCollapsed: false,
    rangeCount: 1,
    getRangeAt: () => range,
    anchorNode: textNode,
    focusNode: textNode,
    removeAllRanges: () => {},
  } as unknown as Selection);
}

describe("useAnnotator integration (real hook → DOM)", () => {
  let rootEl: HTMLElement;
  let passage: HTMLElement;

  beforeEach(() => {
    localStorage.clear();
    passage = document.createElement("div");
    passage.id = "ts-passage";
    passage.innerHTML = "<div>The quick brown fox jumps</div>";
    document.body.appendChild(passage);
    rootEl = document.createElement("div");
    document.body.appendChild(rootEl);
  });

  afterEach(() => {
    document.body.innerHTML = "";
    vi.restoreAllMocks();
  });

  it("auto-highlights yellow on selection, then recolours via the toolbar", async () => {
    const root = createRoot(rootEl);
    await act(async () => {
      root.render(<Harness />);
    });

    const textNode = passage.querySelector("div")!.firstChild as Text;
    mockSelectionOver(textNode, 4, 9); // "quick"

    await act(async () => {
      document.dispatchEvent(new MouseEvent("mouseup", { bubbles: true }));
    });

    // Selecting alone applied a yellow highlight (no colour click needed).
    let mark = passage.querySelector("mark.ts-annot") as HTMLElement | null;
    expect(mark?.textContent).toBe("quick");
    expect(mark?.dataset.color).toBe("yellow");
    expect(latest.toolbar?.container).toBe("passage");
    expect(latest.toolbar?.current.color).toBe("yellow");

    await act(async () => {
      latest.applyColor("blue");
    });
    mark = passage.querySelector("mark.ts-annot") as HTMLElement | null;
    expect(mark?.dataset.color).toBe("blue");

    await act(async () => {
      root.unmount();
    });
  });

  it("keeps marks after a parent re-render of a dangerouslySetInnerHTML passage", async () => {
    document.body.innerHTML = "";
    const host = document.createElement("div");
    document.body.appendChild(host);
    const root = createRoot(host);
    await act(async () => {
      root.render(<App />);
    });

    const textNode = document.querySelector("#ts-passage")!.firstChild as Text;
    mockSelectionOver(textNode, 4, 9);
    await act(async () => {
      document.dispatchEvent(new MouseEvent("mouseup", { bubbles: true }));
    });
    expect(document.querySelector("#ts-passage mark.ts-annot")).not.toBeNull();

    await act(async () => {
      bump();
    });
    expect(document.querySelector("#ts-passage mark.ts-annot")).not.toBeNull();

    await act(async () => {
      root.unmount();
    });
  });
});
