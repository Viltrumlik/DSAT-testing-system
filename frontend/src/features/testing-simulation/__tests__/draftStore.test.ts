import { beforeEach, describe, expect, it } from "vitest";
import { clearDraft, readDraft, writeDraft } from "../services/draftStore";

describe("draftStore — offline answer backup", () => {
  beforeEach(() => localStorage.clear());

  it("round-trips a draft", () => {
    writeDraft(99, { answers: { "1": "A" }, flagged: [1], version: 4, moduleId: 10 });
    expect(readDraft(99, 10)).toEqual({ answers: { "1": "A" }, flagged: [1], version: 4, moduleId: 10 });
  });

  it("is scoped per module — Module 1 work never bleeds into Module 2", () => {
    writeDraft(99, { answers: { "1": "A" }, flagged: [], version: 1, moduleId: 10 });
    expect(readDraft(99, 11)).toBeNull();
  });

  it("returns null for corrupt storage", () => {
    localStorage.setItem("ts.draft.99.10", "{not json");
    expect(readDraft(99, 10)).toBeNull();
  });

  it("clears a draft", () => {
    writeDraft(99, { answers: { "1": "A" }, flagged: [], version: 1, moduleId: 10 });
    clearDraft(99, 10);
    expect(readDraft(99, 10)).toBeNull();
  });
});
