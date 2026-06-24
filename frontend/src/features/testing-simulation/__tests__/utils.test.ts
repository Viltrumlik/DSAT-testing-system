import { describe, expect, it } from "vitest";
import { clamp, formatClock, moduleLimitSeconds } from "../utils/time";
import { parseOptions } from "../utils/options";
import { submitKey } from "../utils/idempotency";
import type { ExamQuestion } from "../types";

describe("formatClock", () => {
  it("formats M:SS with zero padding", () => {
    expect(formatClock(0)).toBe("0:00");
    expect(formatClock(9)).toBe("0:09");
    expect(formatClock(75)).toBe("1:15");
    expect(formatClock(2100)).toBe("35:00");
  });
  it("floors and clamps negatives to 0:00", () => {
    expect(formatClock(-5)).toBe("0:00");
    expect(formatClock(59.9)).toBe("0:59");
  });
});

describe("clamp", () => {
  it("bounds the value", () => {
    expect(clamp(50, 28, 72)).toBe(50);
    expect(clamp(10, 28, 72)).toBe(28);
    expect(clamp(99, 28, 72)).toBe(72);
  });
});

describe("moduleLimitSeconds", () => {
  it("prefers explicit server duration", () => {
    expect(moduleLimitSeconds({ module_duration_seconds: 2100, time_limit_minutes: 35 })).toBe(2100);
  });
  it("falls back to minutes when duration is null", () => {
    expect(moduleLimitSeconds({ module_duration_seconds: null, time_limit_minutes: 32 })).toBe(1920);
  });
  it("is non-negative when both are missing", () => {
    expect(moduleLimitSeconds({ module_duration_seconds: null, time_limit_minutes: null })).toBe(0);
  });
});

describe("parseOptions", () => {
  const base = { id: 1, question_type: "MATH", question_text: "x" } as ExamQuestion;

  it("defaults to A–D when options are absent", () => {
    expect(parseOptions(base).map((o) => o.key)).toEqual(["A", "B", "C", "D"]);
  });
  it("parses a string map", () => {
    const q = { ...base, options: { A: "one", B: "two" } } as ExamQuestion;
    expect(parseOptions(q)).toEqual([
      { key: "A", text: "one", image: undefined },
      { key: "B", text: "two", image: undefined },
    ]);
  });
  it("parses a {text,image} map", () => {
    const q = { ...base, options: { A: { text: "t", image: "/m.png" } } } as ExamQuestion;
    expect(parseOptions(q)[0]).toEqual({ key: "A", text: "t", image: "/m.png" });
  });
});

describe("submitKey", () => {
  it("is stable for the same (attempt, module, version) so retries dedupe", () => {
    expect(submitKey(7, 10, 3)).toBe("submit.7.10.v3");
    expect(submitKey(7, 10, 3)).toBe(submitKey(7, 10, 3));
  });
  it("changes when the version advances (genuine new submit)", () => {
    expect(submitKey(7, 10, 3)).not.toBe(submitKey(7, 10, 4));
  });
});
