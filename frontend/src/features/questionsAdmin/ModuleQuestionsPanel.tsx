"use client";

import * as React from "react";
import Link from "next/link";
import {
  DndContext,
  DragOverlay,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  arrayMove,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import {
  useCreateModuleQuestion,
  useDeleteModuleQuestion,
  useModuleQuestionsQuery,
  useReorderModuleQuestionsBulk,
  useUpdateModuleQuestion,
} from "@/features/questionsAdmin/hooks";
import type { AdminModuleQuestion } from "@/features/questionsAdmin/types";
import { normalizeApiError } from "@/lib/apiError";
import {
  AlertCircle,
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  GripVertical,
  ImagePlus,
  Loader2,
  Plus,
  RefreshCcw,
  Save,
  Trash2,
  X,
} from "lucide-react";
import { STUDIO_FIELD_LABEL, STUDIO_INPUT } from "@/components/studio/primitives";
import { StudioSpinner } from "@/components/studio/StudioSpinner";
import { FormulaToolbar } from "@/components/FormulaToolbar";
import { MathText } from "@/components/MathText";
import {
  allowedQuestionTypesForSubject,
  getModuleProgress,
  questionTypeWarning,
  SAT_MODULE_SCORE_CAP,
  SAT_QUESTION_TYPE_LABEL,
  SAT_SUBJECT_LABEL,
  isSatSubject,
  type SatQuestionType,
  type SatSubject,
} from "@/lib/satRules";

// ─── Draft type ──────────────────────────────────────────────────────────────

/** Answer format shown in the midterm question editor instead of SAT types. */
type MidtermFormat = "mc" | "numeric" | "short_text" | "true_false";

type QuestionDraft = {
  question_type: "MATH" | "READING" | "WRITING";
  question_text: string;
  question_prompt: string;
  is_math_input: boolean;
  option_a: string;
  option_b: string;
  option_c: string;
  option_d: string;
  correct_answer: string;
  explanation: string;
  score: number;
  /** Only meaningful when examKind === "MIDTERM". */
  midtermFormat: MidtermFormat;
};

/** Infer midterm answer format from existing question fields. */
function detectMidtermFormat(q: AdminModuleQuestion): MidtermFormat {
  if (q.is_math_input) return "numeric";
  const a = (q.option_a ?? "").trim().toLowerCase();
  const b = (q.option_b ?? "").trim().toLowerCase();
  if (a === "true" && b === "false" && !(q.option_c ?? "").trim() && !(q.option_d ?? "").trim()) {
    return "true_false";
  }
  return "mc";
}

function questionToDraft(q: AdminModuleQuestion, sectionSubject?: string, examKind?: string): QuestionDraft {
  // Use existing type, but if it's wrong for the subject, fall back to the first allowed type.
  const allowed = allowedQuestionTypesForSubject(sectionSubject);
  const existingType = q.question_type ?? "MATH";
  const resolvedType = (allowed as readonly string[]).includes(existingType)
    ? existingType
    : allowed[0] ?? existingType;
  return {
    question_type: resolvedType as QuestionDraft["question_type"],
    question_text: q.question_text ?? "",
    question_prompt: q.question_prompt ?? "",
    is_math_input: q.is_math_input ?? false,
    option_a: q.option_a ?? "",
    option_b: q.option_b ?? "",
    option_c: q.option_c ?? "",
    option_d: q.option_d ?? "",
    correct_answer: q.correct_answer ?? "",
    explanation: q.explanation ?? "",
    score: q.score ?? 10,
    midtermFormat: examKind === "MIDTERM" ? detectMidtermFormat(q) : "mc",
  };
}

// Re-export canonical tokens under local aliases so the rest of this file
// uses concise names, while the source of truth lives in studio/primitives.ts.
const FIELD_LABEL = STUDIO_FIELD_LABEL;
const INPUT = STUDIO_INPUT;

// ─── Question editor pane ────────────────────────────────────────────────────

function QuestionEditor({
  question,
  testId,
  moduleId,
  sectionSubject,
  examKind,
  scoringScale,
  onSaved,
  onDeleted,
}: {
  question: AdminModuleQuestion;
  testId: number;
  moduleId: number;
  /** PracticeTest.subject — drives SAT type restrictions */
  sectionSubject?: string;
  /** MockExam.kind — "MIDTERM" switches to pedagogical question formats */
  examKind?: string;
  /** SCALE_800 midterms use per-question weights (like SAT); SCALE_100 ignores them. */
  scoringScale?: "SCALE_100" | "SCALE_800";
  onSaved: (updated: AdminModuleQuestion) => void;
  onDeleted: () => void;
}) {
  const update = useUpdateModuleQuestion(testId, moduleId);
  const del = useDeleteModuleQuestion(testId, moduleId);
  const isMidterm = examKind === "MIDTERM";
  // SCALE_800 midterms feed the SAT 200–800 curve, which weights questions by
  // their `score`. Surface the weight selector for those; SCALE_100 stays equal-weight.
  const isScale800Midterm = isMidterm && scoringScale === "SCALE_800";

  const [draft, setDraft] = React.useState<QuestionDraft>(() => questionToDraft(question, sectionSubject, examKind));
  const [confirmDelete, setConfirmDelete] = React.useState(false);
  const [saveOk, setSaveOk] = React.useState(false);

  type ImageKey = "question" | "a" | "b" | "c" | "d";
  const [imageFiles, setImageFiles] = React.useState<Partial<Record<ImageKey, File>>>({});
  const [clearImages, setClearImages] = React.useState<Partial<Record<ImageKey, boolean>>>({});

  // Reset draft when question changes
  React.useEffect(() => {
    setDraft(questionToDraft(question, sectionSubject, examKind));
    setSaveOk(false);
    setConfirmDelete(false);
    setImageFiles({});
    setClearImages({});
  }, [question.id, sectionSubject, examKind]);

  const patch = (p: Partial<QuestionDraft>) => setDraft((d) => ({ ...d, ...p }));

  const handleSave = async () => {
    setSaveOk(false);

    // Derive backend fields from midtermFormat when editing a midterm question.
    // The underlying model uses is_math_input + option_a/b/c/d regardless of format.
    const effectiveDraft = (() => {
      if (!isMidterm) return draft;
      const fmt = draft.midtermFormat;
      if (fmt === "numeric" || fmt === "short_text") {
        return { ...draft, is_math_input: true, option_a: "", option_b: "", option_c: "", option_d: "" };
      }
      if (fmt === "true_false") {
        return { ...draft, is_math_input: false, option_a: "True", option_b: "False", option_c: "", option_d: "" };
      }
      // mc — use draft as-is
      return { ...draft, is_math_input: false };
    })();

    const hasFiles = Object.keys(imageFiles).length > 0 || Object.values(clearImages).some(Boolean);
    let data: FormData | Record<string, unknown>;
    if (hasFiles) {
      const fd = new FormData();
      fd.append("question_type", effectiveDraft.question_type);
      fd.append("question_text", effectiveDraft.question_text);
      fd.append("question_prompt", effectiveDraft.question_prompt);
      fd.append("is_math_input", String(effectiveDraft.is_math_input));
      fd.append("option_a", effectiveDraft.option_a);
      fd.append("option_b", effectiveDraft.option_b);
      fd.append("option_c", effectiveDraft.option_c);
      fd.append("option_d", effectiveDraft.option_d);
      fd.append("correct_answer", effectiveDraft.correct_answer);
      fd.append("explanation", effectiveDraft.explanation);
      fd.append("score", String(effectiveDraft.score));
      if (imageFiles.question) fd.append("question_image", imageFiles.question);
      if (imageFiles.a) fd.append("option_a_image", imageFiles.a);
      if (imageFiles.b) fd.append("option_b_image", imageFiles.b);
      if (imageFiles.c) fd.append("option_c_image", imageFiles.c);
      if (imageFiles.d) fd.append("option_d_image", imageFiles.d);
      if (clearImages.question) fd.append("clear_question_image", "true");
      if (clearImages.a) fd.append("clear_option_a_image", "true");
      if (clearImages.b) fd.append("clear_option_b_image", "true");
      if (clearImages.c) fd.append("clear_option_c_image", "true");
      if (clearImages.d) fd.append("clear_option_d_image", "true");
      data = fd;
    } else {
      data = {
        question_type: effectiveDraft.question_type,
        question_text: effectiveDraft.question_text,
        question_prompt: effectiveDraft.question_prompt,
        is_math_input: effectiveDraft.is_math_input,
        option_a: effectiveDraft.option_a,
        option_b: effectiveDraft.option_b,
        option_c: effectiveDraft.option_c,
        option_d: effectiveDraft.option_d,
        correct_answer: effectiveDraft.correct_answer,
        explanation: effectiveDraft.explanation,
        score: effectiveDraft.score,
      };
    }
    try {
      const result = await update.mutateAsync({ questionId: question.id, data });
      setSaveOk(true);
      setImageFiles({});
      setClearImages({});
      onSaved(result as AdminModuleQuestion);
      setTimeout(() => setSaveOk(false), 2000);
    } catch {
      // error shown via update.error
    }
  };

  const handleDelete = async () => {
    try {
      await del.mutateAsync(question.id);
      onDeleted();
    } catch {
      // error shown via del.error
    }
  };

  // For midterms, whether choices are shown is derived from midtermFormat,
  // not from is_math_input (which is set on save, not during editing).
  const isMC = isMidterm
    ? (draft.midtermFormat === "mc" || draft.midtermFormat === "true_false")
    : !draft.is_math_input;
  const isBusy = update.isPending || del.isPending;

  // ── SAT subject awareness ──────────────────────────────────────────────────
  const allowedTypes = allowedQuestionTypesForSubject(sectionSubject);
  const typeWarning = questionTypeWarning(draft.question_type, sectionSubject);

  const updateErr = update.isError && update.error ? normalizeApiError(update.error).message : null;
  const deleteErr = del.isError && del.error ? normalizeApiError(del.error).message : null;

  // ── Formula insertion ──────────────────────────────────────────────────────
  // Tracks whichever textarea/input currently has focus so the toolbar can
  // insert at the correct cursor position without needing to know the field.
  const activeFieldRef = React.useRef<{
    el: HTMLTextAreaElement | HTMLInputElement;
    setVal: (v: string) => void;
  } | null>(null);

  const handleFormulaInsert = React.useCallback(
    (snippet: string, cursorOffset: number) => {
      const active = activeFieldRef.current;
      if (!active) return;
      const { el, setVal } = active;
      // Read directly from el.value (not a React state closure) to get the
      // current value regardless of batched React updates.
      const start = el.selectionStart ?? el.value.length;
      const end = el.selectionEnd ?? el.value.length;
      const newVal = el.value.slice(0, start) + snippet + el.value.slice(end);
      const newCursorPos = start + cursorOffset;
      setVal(newVal);
      // Wait for React to flush the state update and repaint the DOM before
      // restoring focus + cursor — otherwise setSelectionRange runs on stale DOM.
      requestAnimationFrame(() => {
        el.focus();
        el.setSelectionRange(newCursorPos, newCursorPos);
      });
    },
    [],
  );

  return (
    <div className="flex h-full flex-col">
      {/* Header — save button row (never scrolls) */}
      <div className="shrink-0 border-b border-border bg-card">
        <div className="flex items-center justify-between gap-3 px-5 py-3">
          <div className="min-w-0">
            <p className="text-xs font-extrabold text-foreground">Q{question.order + 1} — #{question.id}</p>
            <p className="text-[10px] text-muted-foreground">Question editor</p>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            {saveOk && (
              <span className="flex items-center gap-1 text-xs font-semibold text-emerald-600">
                <CheckCircle2 className="h-3.5 w-3.5" />
                Saved
              </span>
            )}
            <button
              type="button"
              disabled={isBusy}
              onClick={() => void handleSave()}
              className="inline-flex items-center gap-1.5 rounded-xl bg-primary px-3 py-1.5 text-xs font-bold text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
            >
              {update.isPending ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Save className="h-3.5 w-3.5" />
              )}
              Save
            </button>
          </div>
        </div>
      </div>

      {/* Formula toolbar — always visible, never scrolls away */}
      <div className="shrink-0 border-b border-border bg-card">
        <div className="px-3 pt-2 pb-0">
          <p className="text-[9px] font-bold uppercase tracking-widest text-muted-foreground/50 mb-1">
            Formula insert — click a symbol, then type in a field below
          </p>
        </div>
        <FormulaToolbar onInsert={handleFormulaInsert} />
      </div>

      {/* Error banners */}
      {(updateErr || deleteErr) && (
        <div className="mx-5 mt-3 flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 shrink-0">
          <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
          <span>{updateErr ?? deleteErr}</span>
        </div>
      )}

      {/* Scrollable form body */}
      <div className="flex-1 overflow-y-auto">
      <div className="space-y-5 p-5">

        {/* Type row — midterms use answer-format selector; SAT uses type + score */}
        {isMidterm ? (
          <div className={isScale800Midterm ? "grid grid-cols-2 gap-4" : ""}>
            <div>
              <label className={FIELD_LABEL}>Answer format</label>
              <select
                className={INPUT}
                value={draft.midtermFormat}
                onChange={(e) => patch({ midtermFormat: e.target.value as MidtermFormat })}
              >
                <option value="mc">Multiple choice (A / B / C / D)</option>
                <option value="numeric">Numeric (student enters a number)</option>
                <option value="short_text">Short text (student types an answer)</option>
                <option value="true_false">True / False</option>
              </select>
            </div>
            {/* 800-point midterms weight questions onto the SAT curve. */}
            {isScale800Midterm && (
              <div>
                <label className={FIELD_LABEL}>Score weight</label>
                <select
                  className={INPUT}
                  value={draft.score}
                  onChange={(e) => patch({ score: Number(e.target.value) })}
                >
                  <option value={10}>10 ball</option>
                  <option value={20}>20 ball</option>
                  <option value={40}>40 ball</option>
                </select>
              </div>
            )}
          </div>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className={FIELD_LABEL}>Question type</label>
                <select
                  className={INPUT}
                  value={draft.question_type}
                  onChange={(e) => patch({ question_type: e.target.value as QuestionDraft["question_type"] })}
                >
                  {allowedTypes.map((t) => (
                    <option key={t} value={t}>
                      {SAT_QUESTION_TYPE_LABEL[t as SatQuestionType] ?? t}
                    </option>
                  ))}
                </select>
                {/* SAT type mismatch warning */}
                {typeWarning && (
                  <div className="mt-1.5 flex items-start gap-1.5 rounded-lg border border-amber-200 bg-amber-50 px-2.5 py-1.5">
                    <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0 text-amber-600" />
                    <p className="text-[11px] font-semibold leading-snug text-amber-800">{typeWarning}</p>
                  </div>
                )}
              </div>
              <div>
                <label className={FIELD_LABEL}>Score weight</label>
                <select
                  className={INPUT}
                  value={draft.score}
                  onChange={(e) => patch({ score: Number(e.target.value) })}
                >
                  <option value={10}>10 ball</option>
                  <option value={20}>20 ball</option>
                  <option value={40}>40 ball</option>
                </select>
              </div>
            </div>

            {/* Math input toggle — SAT only */}
            <div className="flex items-center gap-3">
              <input
                type="checkbox"
                id="is_math_input"
                checked={draft.is_math_input}
                onChange={(e) => patch({ is_math_input: e.target.checked })}
                className="h-4 w-4 rounded border-border accent-primary"
              />
              <label htmlFor="is_math_input" className="text-sm font-semibold text-foreground cursor-pointer select-none">
                Student types numeric answer (no A/B/C/D choices)
              </label>
            </div>
          </>
        )}

        {/* Question text */}
        <div>
          <label className={FIELD_LABEL}>Question text (stem)</label>
          <textarea
            className={`${INPUT} min-h-[140px] leading-relaxed`}
            placeholder="Enter the full question text here. LaTeX math is supported: \( x^2 + 1 = 0 \)"
            value={draft.question_text}
            onChange={(e) => patch({ question_text: e.target.value })}
            onFocus={(e) => {
              activeFieldRef.current = {
                el: e.currentTarget,
                setVal: (v) => patch({ question_text: v }),
              };
            }}
          />
          {draft.question_text.trim() && (
            <div className="mt-2 rounded-xl border border-border/60 bg-surface-2/50 px-3 py-2.5">
              <p className="mb-1.5 text-[9px] font-bold uppercase tracking-widest text-muted-foreground/60">
                Preview
              </p>
              <MathText text={draft.question_text} className="text-sm leading-relaxed text-foreground" />
            </div>
          )}
          {/* Question image */}
          <div className="mt-3">
            <label className={FIELD_LABEL}>Question image (optional)</label>
            <div className="mt-1 space-y-2">
              {question.question_image && !clearImages.question && !imageFiles.question && (
                <div className="flex items-center gap-2">
                  <img src={question.question_image} alt="Question" className="max-h-32 rounded-xl border border-border object-contain" />
                  <button
                    type="button"
                    onClick={() => setClearImages((c) => ({ ...c, question: true }))}
                    className="inline-flex items-center gap-1 rounded-lg border border-red-200 bg-red-50 px-2 py-1 text-xs font-semibold text-red-700 hover:bg-red-100 transition-colors"
                  >
                    <X className="h-3 w-3" /> Remove
                  </button>
                </div>
              )}
              {imageFiles.question && (
                <div className="flex items-center gap-2">
                  <img src={URL.createObjectURL(imageFiles.question)} alt="Preview" className="max-h-32 rounded-xl border border-border object-contain" />
                  <button
                    type="button"
                    onClick={() => setImageFiles((f) => { const n = { ...f }; delete n.question; return n; })}
                    className="inline-flex items-center gap-1 rounded-lg border border-border bg-card px-2 py-1 text-xs font-semibold text-muted-foreground hover:bg-surface-2 transition-colors"
                  >
                    <X className="h-3 w-3" /> Cancel
                  </button>
                </div>
              )}
              <label className="inline-flex cursor-pointer items-center gap-2 rounded-xl border border-dashed border-border bg-surface-2/30 px-3 py-2 text-xs font-semibold text-muted-foreground hover:bg-surface-2/60 transition-colors">
                <ImagePlus className="h-3.5 w-3.5" />
                {imageFiles.question ? "Change image" : question.question_image && !clearImages.question ? "Replace image" : "Upload image"}
                <input
                  type="file"
                  accept="image/*"
                  className="sr-only"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) { setImageFiles((prev) => ({ ...prev, question: f })); setClearImages((c) => ({ ...c, question: false })); }
                  }}
                />
              </label>
            </div>
          </div>
        </div>

        {/* Secondary prompt */}
        <div>
          <label className={FIELD_LABEL}>Stimulus / passage excerpt (optional)</label>
          <textarea
            className={`${INPUT} min-h-[80px] leading-relaxed`}
            placeholder="Secondary text shown above the answer choices — e.g. a short passage excerpt or graph description."
            value={draft.question_prompt}
            onChange={(e) => patch({ question_prompt: e.target.value })}
            onFocus={(e) => {
              activeFieldRef.current = {
                el: e.currentTarget,
                setVal: (v) => patch({ question_prompt: v }),
              };
            }}
          />
        </div>

        {/* MC choices — True/False mode shows static True/False labels; regular MC shows editable A-D */}
        {isMC && draft.midtermFormat === "true_false" ? (
          <div className="rounded-2xl border border-border bg-surface-2/30 p-4">
            <p className={`${FIELD_LABEL} mb-3`}>Answer choices (True / False)</p>
            <div className="flex gap-3">
              {(["True", "False"] as const).map((label) => (
                <div
                  key={label}
                  className="flex flex-1 items-center gap-2 rounded-xl border border-border bg-card px-4 py-2.5 text-sm font-semibold text-foreground"
                >
                  <span className="flex h-6 w-6 items-center justify-center rounded-full border border-border bg-surface-2 text-xs font-extrabold text-muted-foreground">
                    {label === "True" ? "A" : "B"}
                  </span>
                  {label}
                </div>
              ))}
            </div>
          </div>
        ) : isMC && (
          <div className="rounded-2xl border border-border bg-surface-2/30 p-4 space-y-3">
            <p className={FIELD_LABEL}>Answer choices</p>
            {(["a", "b", "c", "d"] as const).map((letter) => {
              const key = `option_${letter}` as keyof QuestionDraft;
              const val = draft[key] as string;
              return (
                <div key={letter} className="space-y-1">
                  <div className="flex items-start gap-3">
                    <div className="mt-2 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-border bg-card text-xs font-extrabold text-foreground">
                      {letter.toUpperCase()}
                    </div>
                    <input
                      className={`${INPUT} flex-1`}
                      placeholder={`Option ${letter.toUpperCase()}`}
                      value={val}
                      onChange={(e) => patch({ [key]: e.target.value } as Partial<QuestionDraft>)}
                      onFocus={(e) => {
                        activeFieldRef.current = {
                          el: e.currentTarget,
                          setVal: (v) => patch({ [key]: v } as Partial<QuestionDraft>),
                        };
                      }}
                    />
                  </div>
                  {val.trim() && (
                    <div className="ml-9 rounded-lg border border-border/50 bg-card px-2.5 py-1.5">
                      <MathText text={val} className="text-xs leading-relaxed text-foreground" />
                    </div>
                  )}
                  {/* Option image */}
                  <div className="ml-9 flex flex-wrap items-center gap-2">
                    {(() => {
                      const imgKey = letter as ImageKey;
                      const existingImg = question[`option_${letter}_image` as keyof typeof question] as string | null | undefined;
                      const file = imageFiles[imgKey];
                      const cleared = clearImages[imgKey];
                      return (
                        <>
                          {existingImg && !cleared && !file && (
                            <>
                              <img src={existingImg} alt={`Option ${letter.toUpperCase()}`} className="max-h-16 rounded-lg border border-border object-contain" />
                              <button
                                type="button"
                                onClick={() => setClearImages((c) => ({ ...c, [imgKey]: true }))}
                                className="inline-flex items-center gap-1 rounded-lg border border-red-200 bg-red-50 px-2 py-1 text-xs font-semibold text-red-700 hover:bg-red-100 transition-colors"
                              >
                                <X className="h-3 w-3" /> Remove
                              </button>
                            </>
                          )}
                          {file && (
                            <>
                              <img src={URL.createObjectURL(file)} alt="Preview" className="max-h-16 rounded-lg border border-border object-contain" />
                              <button
                                type="button"
                                onClick={() => setImageFiles((f) => { const n = { ...f }; delete n[imgKey]; return n; })}
                                className="inline-flex items-center gap-1 rounded-lg border border-border bg-card px-2 py-1 text-xs font-semibold text-muted-foreground hover:bg-surface-2 transition-colors"
                              >
                                <X className="h-3 w-3" /> Cancel
                              </button>
                            </>
                          )}
                          <label className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg border border-dashed border-border bg-surface-2/30 px-2 py-1 text-xs font-semibold text-muted-foreground hover:bg-surface-2/60 transition-colors">
                            <ImagePlus className="h-3 w-3" />
                            {file ? "Change" : existingImg && !cleared ? "Replace" : "Add image"}
                            <input
                              type="file"
                              accept="image/*"
                              className="sr-only"
                              onChange={(e) => {
                                const f = e.target.files?.[0];
                                if (f) { setImageFiles((prev) => ({ ...prev, [imgKey]: f })); setClearImages((c) => ({ ...c, [imgKey]: false })); }
                              }}
                            />
                          </label>
                        </>
                      );
                    })()}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Correct answer — format-aware for midterms */}
        <div>
          {isMidterm && draft.midtermFormat === "true_false" ? (
            <>
              <label className={FIELD_LABEL}>Correct answer</label>
              <div className="flex gap-3 mt-1">
                {(["True", "False"] as const).map((label, i) => {
                  const letter = i === 0 ? "A" : "B";
                  const isSelected = draft.correct_answer.toUpperCase() === letter;
                  return (
                    <button
                      key={label}
                      type="button"
                      onClick={() => patch({ correct_answer: letter })}
                      className={`flex flex-1 items-center justify-center gap-2 rounded-xl border px-4 py-2.5 text-sm font-bold transition-colors ${
                        isSelected
                          ? "border-emerald-400 bg-emerald-50 text-emerald-800"
                          : "border-border bg-card text-foreground hover:bg-surface-2"
                      }`}
                    >
                      {isSelected && <CheckCircle2 className="h-4 w-4 text-emerald-600 shrink-0" />}
                      {label}
                    </button>
                  );
                })}
              </div>
            </>
          ) : isMidterm && draft.midtermFormat === "mc" ? (
            <>
              <label className={FIELD_LABEL}>Correct answer</label>
              <div className="flex gap-2 mt-1">
                {(["A", "B", "C", "D"] as const).map((letter) => {
                  const isSelected = draft.correct_answer.toUpperCase() === letter;
                  return (
                    <button
                      key={letter}
                      type="button"
                      onClick={() => patch({ correct_answer: letter })}
                      className={`flex h-10 w-10 items-center justify-center rounded-xl border text-sm font-extrabold transition-colors ${
                        isSelected
                          ? "border-emerald-400 bg-emerald-50 text-emerald-800"
                          : "border-border bg-card text-foreground hover:bg-surface-2"
                      }`}
                    >
                      {letter}
                    </button>
                  );
                })}
              </div>
            </>
          ) : (
            <>
              <label className={FIELD_LABEL}>
                {isMidterm && draft.midtermFormat === "numeric"
                  ? "Correct answer (number — separate multiple valid forms with commas)"
                  : isMidterm && draft.midtermFormat === "short_text"
                  ? "Correct answer (text — case-insensitive, comma-separated alternatives)"
                  : isMC
                  ? "Correct answer (A, B, C, or D)"
                  : "Correct answer (comma-separated for multiple valid forms, e.g. 2/3, 0.667)"}
              </label>
              <input
                className={INPUT}
                placeholder={
                  isMidterm && draft.midtermFormat === "numeric"
                    ? "e.g. 42 or 2/3, 0.667"
                    : isMidterm && draft.midtermFormat === "short_text"
                    ? "e.g. Paris or paris"
                    : isMC
                    ? "A"
                    : "e.g. 42 or 2/3, 0.666, 0.667"
                }
                value={draft.correct_answer}
                onChange={(e) => patch({ correct_answer: e.target.value })}
                onFocus={(e) => {
                  activeFieldRef.current = {
                    el: e.currentTarget,
                    setVal: (v) => patch({ correct_answer: v }),
                  };
                }}
              />
              {!isMidterm && isMC && (
                <p className="mt-1 text-[11px] text-muted-foreground">
                  Must exactly match one of the choice letters above (case-insensitive).
                </p>
              )}
            </>
          )}
        </div>

        {/* Explanation */}
        <div>
          <label className={FIELD_LABEL}>Explanation / solution rationale</label>
          <textarea
            className={`${INPUT} min-h-[100px] leading-relaxed`}
            placeholder="Explain why the correct answer is right. Students see this after the test."
            value={draft.explanation}
            onChange={(e) => patch({ explanation: e.target.value })}
            onFocus={(e) => {
              activeFieldRef.current = {
                el: e.currentTarget,
                setVal: (v) => patch({ explanation: v }),
              };
            }}
          />
        </div>

        {/* Save button (bottom) */}
        <div className="flex items-center justify-between border-t border-border pt-4">
          <button
            type="button"
            disabled={isBusy}
            onClick={() => void handleSave()}
            className="inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-2 text-sm font-bold text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
          >
            {update.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Save className="h-4 w-4" />
            )}
            {update.isPending ? "Saving…" : "Save question"}
          </button>

          {/* Delete */}
          {confirmDelete ? (
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-red-700">Delete this question?</span>
              <button
                type="button"
                disabled={del.isPending}
                onClick={() => void handleDelete()}
                className="rounded-xl bg-red-600 px-3 py-1.5 text-xs font-bold text-white hover:bg-red-700 disabled:opacity-50 transition-colors"
              >
                {del.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : "Yes, delete"}
              </button>
              <button
                type="button"
                onClick={() => setConfirmDelete(false)}
                className="rounded-xl border border-border bg-card px-3 py-1.5 text-xs font-bold text-foreground hover:bg-surface-2 transition-colors"
              >
                Cancel
              </button>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => setConfirmDelete(true)}
              className="inline-flex items-center gap-1.5 rounded-xl border border-red-200 bg-red-50 px-3 py-1.5 text-xs font-bold text-red-700 hover:bg-red-100 transition-colors"
            >
              <Trash2 className="h-3.5 w-3.5" />
              Delete
            </button>
          )}
        </div>
      </div>
      </div>
    </div>
  );
}

// ─── Sortable question row ────────────────────────────────────────────────────

function SortableQRow({
  q,
  index,
  selected,
  reordering,
  hasTypeMismatch,
  examKind,
  onSelect,
}: {
  q: AdminModuleQuestion;
  index: number;
  selected: boolean;
  reordering: boolean;
  /** True when this question's type is wrong for the section subject */
  hasTypeMismatch?: boolean;
  examKind?: string;
  onSelect: () => void;
}) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: q.id });

  const style: React.CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.4 : 1,
    zIndex: isDragging ? 10 : undefined,
  };

  const typeColor: Record<string, string> = {
    MATH: "bg-purple-100 text-purple-700",
    READING: "bg-blue-100 text-blue-700",
    WRITING: "bg-teal-100 text-teal-700",
  };
  const color = typeColor[q.question_type] ?? "bg-surface-2 text-muted-foreground";
  const isMidtermRow = examKind === "MIDTERM";

  // For midterm rows, show the answer format instead of SAT type.
  const midtermFormatLabel = (() => {
    if (!isMidtermRow) return null;
    const fmt = detectMidtermFormat(q);
    if (fmt === "true_false") return { label: "T/F", color: "bg-violet-100 text-violet-700" };
    if (fmt === "numeric") return { label: "Num", color: "bg-amber-100 text-amber-700" };
    if (fmt === "short_text") return { label: "Text", color: "bg-teal-100 text-teal-700" };
    return { label: "MC", color: "bg-blue-100 text-blue-700" };
  })();

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={`group flex w-full items-start gap-1.5 rounded-xl border transition-colors ${
        selected
          ? "border-primary/40 bg-primary/8 ring-1 ring-primary/20"
          : "border-border bg-card hover:border-primary/20 hover:bg-surface-2/60"
      } ${reordering ? "pointer-events-none" : ""}`}
    >
      {/* Drag handle */}
      <button
        type="button"
        {...attributes}
        {...listeners}
        className="flex shrink-0 cursor-grab items-center self-stretch rounded-l-xl px-1.5 text-muted-foreground/40 hover:text-muted-foreground active:cursor-grabbing transition-colors focus:outline-none"
        aria-label="Drag to reorder"
        tabIndex={-1}
      >
        <GripVertical className="h-3.5 w-3.5" />
      </button>

      {/* Row body — clicking selects the question */}
      <button
        type="button"
        onClick={onSelect}
        className="min-w-0 flex-1 py-3 pr-3 text-left"
      >
        <div className="mb-1 flex items-center gap-1.5">
          <span className="shrink-0 rounded-md bg-surface-2 px-1.5 py-0.5 text-[9px] font-extrabold tabular-nums text-muted-foreground">
            Q{index + 1}
          </span>
          {midtermFormatLabel ? (
            <span className={`shrink-0 rounded-md px-1.5 py-0.5 text-[9px] font-extrabold uppercase ${midtermFormatLabel.color}`}>
              {midtermFormatLabel.label}
            </span>
          ) : (
            <span className={`shrink-0 rounded-md px-1.5 py-0.5 text-[9px] font-extrabold uppercase ${color}`}>
              {q.question_type}
            </span>
          )}
          {!isMidtermRow && q.is_math_input && (
            <span className="shrink-0 rounded-md bg-amber-100 px-1.5 py-0.5 text-[9px] font-extrabold uppercase text-amber-700">
              INPUT
            </span>
          )}
          {!isMidtermRow && (
            <span className="shrink-0 rounded-md bg-emerald-100 px-1.5 py-0.5 text-[9px] font-extrabold tabular-nums text-emerald-700">
              {q.score ?? 10}b
            </span>
          )}
          {hasTypeMismatch && (
            <span title="Wrong question type for this section">
              <AlertTriangle className="h-3 w-3 shrink-0 text-amber-500" />
            </span>
          )}
        </div>
        <p className="line-clamp-2 text-xs font-semibold leading-snug text-foreground">
          {q.question_text?.trim() || <em className="text-muted-foreground/50">No text yet</em>}
        </p>
      </button>
    </div>
  );
}

/** Ghost card shown under the pointer during a drag */
function DragGhostRow({ q, index }: { q: AdminModuleQuestion; index: number }) {
  const typeColor: Record<string, string> = {
    MATH: "bg-purple-100 text-purple-700",
    READING: "bg-blue-100 text-blue-700",
    WRITING: "bg-teal-100 text-teal-700",
  };
  const color = typeColor[q.question_type] ?? "bg-surface-2 text-muted-foreground";

  return (
    <div className="flex w-72 items-start gap-1.5 rounded-xl border border-primary/40 bg-card shadow-xl ring-1 ring-primary/20">
      <div className="flex shrink-0 cursor-grabbing items-center self-stretch rounded-l-xl px-1.5 text-muted-foreground">
        <GripVertical className="h-3.5 w-3.5" />
      </div>
      <div className="min-w-0 flex-1 py-3 pr-3">
        <div className="mb-1 flex items-center gap-1.5">
          <span className="shrink-0 rounded-md bg-surface-2 px-1.5 py-0.5 text-[9px] font-extrabold tabular-nums text-muted-foreground">
            Q{index + 1}
          </span>
          <span className={`shrink-0 rounded-md px-1.5 py-0.5 text-[9px] font-extrabold uppercase ${color}`}>
            {q.question_type}
          </span>
        </div>
        <p className="line-clamp-1 text-xs font-semibold leading-snug text-foreground">
          {q.question_text?.trim() || <em className="text-muted-foreground/50">No text yet</em>}
        </p>
      </div>
    </div>
  );
}

// ─── Main panel ──────────────────────────────────────────────────────────────

export default function ModuleQuestionsPanel(props: {
  testId: number;
  moduleId: number;
  /** Optional pack/exam context — enriches the top-bar breadcrumb. */
  packId?: number;
  packTitle?: string;
  sectionSubject?: string;
  moduleOrder?: string;
  /** Override the "back" link destination. Default: /builder/pastpapers */
  backHref?: string;
  /** Override the "back" link label. Default: "Past papers" */
  backLabel?: string;
  /** MockExam.kind — "MIDTERM" enables pedagogical question formats */
  examKind?: string;
  /** MockExam.midterm_scoring_scale — SCALE_800 exposes per-question weights. */
  scoringScale?: "SCALE_100" | "SCALE_800";
}) {
  const { testId, moduleId, packId, packTitle, sectionSubject, moduleOrder, backHref, backLabel, examKind, scoringScale } = props;

  const {
    data: questions = [],
    isLoading,
    isError,
    error,
    refetch,
    isFetching,
  } = useModuleQuestionsQuery(testId, moduleId);

  const create = useCreateModuleQuestion(testId, moduleId);
  const reorderBulk = useReorderModuleQuestionsBulk(testId, moduleId);

  const [selectedId, setSelectedId] = React.useState<number | null>(null);

  // ── Local optimistic ordering state ──────────────────────────────────────
  // The local order is updated immediately on drag-end (optimistic); the
  // single bulk-reorder API call reconciles the server in one round-trip.
  const [localOrder, setLocalOrder] = React.useState<number[]>([]);

  React.useEffect(() => {
    // Only sync from server when no reorder mutation is in flight.
    if (reorderBulk.isPending) return;
    setLocalOrder(questions.map((q) => q.id));
  }, [questions, reorderBulk.isPending]);

  // Derived: questions ordered by localOrder (falls back to server order)
  const orderedQuestions = React.useMemo(() => {
    if (localOrder.length === 0) return questions;
    const byId = new Map(questions.map((q) => [q.id, q]));
    return localOrder.map((id) => byId.get(id)).filter(Boolean) as AdminModuleQuestion[];
  }, [localOrder, questions]);

  // Auto-select first question when list loads
  React.useEffect(() => {
    if (questions.length > 0 && selectedId === null) {
      setSelectedId(questions[0].id);
    }
  }, [questions, selectedId]);

  const selectedQ = orderedQuestions.find((q) => q.id === selectedId) ?? null;

  // ── DnD sensors ──────────────────────────────────────────────────────────
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
  );

  const [activeId, setActiveId] = React.useState<number | null>(null);
  const activeQ = activeId != null
    ? orderedQuestions.find((q) => q.id === activeId) ?? null
    : null;
  const activeIndex = activeId != null ? orderedQuestions.findIndex((q) => q.id === activeId) : -1;

  const handleDragStart = React.useCallback((event: DragStartEvent) => {
    setActiveId(Number(event.active.id));
  }, []);

  const handleDragEnd = React.useCallback(
    async (event: DragEndEvent) => {
      const { active, over } = event;
      setActiveId(null);

      if (!over || active.id === over.id) return;

      const fromIdx = localOrder.indexOf(Number(active.id));
      const toIdx = localOrder.indexOf(Number(over.id));
      if (fromIdx === -1 || toIdx === -1) return;

      // Optimistic update — immediate visual feedback before the API responds.
      const newOrder = arrayMove(localOrder, fromIdx, toIdx);
      setLocalOrder(newOrder);

      // Single atomic bulk-reorder: one round-trip, one invalidation.
      await reorderBulk.mutateAsync(newOrder);
    },
    [localOrder, reorderBulk],
  );

  const listErrMsg = isError && error ? normalizeApiError(error).message : null;
  const reorderErrMsg =
    reorderBulk.isError && reorderBulk.error ? normalizeApiError(reorderBulk.error).message : null;
  const createErrMsg =
    create.isError && create.error ? normalizeApiError(create.error).message : null;

  const mutationBusy = create.isPending || reorderBulk.isPending;

  // ── Score calculator ──────────────────────────────────────────────────────
  const totalScore = React.useMemo(
    () => questions.reduce((sum, q) => sum + (q.score ?? 10), 0),
    [questions],
  );

  // ── SAT progress ───────────────────────────────────────────────────────────
  // Computed before handleAdd so `atCapacity` is in scope for the guard.
  const progress = getModuleProgress(questions.length, sectionSubject);
  const moduleOrderNum = (() => {
    const match = moduleOrder?.match(/\d+/);
    return match ? Number(match[0]) : 1;
  })();
  // Count questions with wrong type for the subject
  const allowedTypesForSubject = allowedQuestionTypesForSubject(sectionSubject);
  const typeMismatchIds = new Set(
    questions
      .filter((q) => !allowedTypesForSubject.includes(q.question_type as SatQuestionType))
      .map((q) => q.id),
  );
  const isSat = isSatSubject(sectionSubject ?? "");
  // True when the module is at or over the SAT question limit — adding is blocked.
  const atCapacity =
    isSat && progress.required !== null && questions.length >= progress.required;

  const handleAdd = async () => {
    // Guard: never fire when the module is already at SAT capacity.
    // The button is disabled at this point, but this protects against stale clicks.
    if (atCapacity) return;
    const result = await create.mutateAsync();
    if (result && typeof result === "object" && "id" in result) {
      setSelectedId((result as AdminModuleQuestion).id);
    }
  };

  return (
    <div className="flex h-full flex-col">
      {/* Top bar */}
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0">
          <Link
            href={backHref ?? `/builder/pastpapers`}
            className="inline-flex items-center gap-1.5 text-sm font-semibold text-muted-foreground hover:text-foreground transition-colors shrink-0"
          >
            <ArrowLeft className="h-4 w-4" />
            {backLabel ?? "Past papers"}
          </Link>
          {packId && packTitle ? (
            <>
              <span className="text-muted-foreground/30">/</span>
              <span className="text-sm font-semibold text-muted-foreground truncate max-w-[160px]" title={packTitle}>
                {packTitle}
              </span>
              <span className="text-muted-foreground/30">/</span>
              <div className="min-w-0">
                <p className="text-sm font-extrabold text-foreground leading-tight">
                  {sectionSubject === "MATH" ? "Mathematics" : sectionSubject === "READING_WRITING" ? "Reading & Writing" : `Test #${testId}`}
                  {moduleOrder ? ` · ${moduleOrder}` : ` · Module #${moduleId}`}
                </p>
                <p className="text-xs text-muted-foreground">
                  {isLoading ? "Loading…" : (
                    isSat
                      ? <span className={progress.complete ? "text-emerald-600 font-bold" : progress.over ? "text-red-600 font-bold" : ""}>
                          {progress.label} questions
                        </span>
                      : `${questions.length} question${questions.length !== 1 ? "s" : ""}`
                  )}
                </p>
              </div>
            </>
          ) : (
            <>
              <span className="text-muted-foreground/30">/</span>
              <div>
                <p className="text-sm font-extrabold text-foreground">
                  Test #{testId} · Module #{moduleId}
                </p>
                <p className="text-xs text-muted-foreground">
                  {isLoading ? "Loading…" : `${questions.length} question${questions.length !== 1 ? "s" : ""}`}
                </p>
              </div>
            </>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => void refetch()}
            disabled={isFetching}
            className="inline-flex items-center gap-1.5 rounded-xl border border-border bg-card px-3 py-1.5 text-xs font-bold text-foreground hover:bg-surface-2 disabled:opacity-50 transition-colors"
          >
            <RefreshCcw className={`h-3.5 w-3.5 ${isFetching ? "animate-spin" : ""}`} />
            Refresh
          </button>
          {atCapacity ? (
            <div className="flex items-center gap-2">
              <span className="text-[11px] font-semibold text-muted-foreground">
                Module full ({progress.required}/{progress.required})
              </span>
              <button
                type="button"
                disabled
                title={`This module already has the maximum ${progress.required} questions for a ${sectionSubject === "MATH" ? "Mathematics" : "Reading & Writing"} module.`}
                className="inline-flex cursor-not-allowed items-center gap-1.5 rounded-xl bg-surface-2 px-3 py-1.5 text-xs font-bold text-muted-foreground opacity-60"
              >
                <Plus className="h-3.5 w-3.5" />
                Add question
              </button>
            </div>
          ) : (
            <button
              type="button"
              disabled={mutationBusy}
              onClick={() => void handleAdd()}
              className="inline-flex items-center gap-1.5 rounded-xl bg-primary px-3 py-1.5 text-xs font-bold text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
            >
              {create.isPending ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Plus className="h-3.5 w-3.5" />
              )}
              Add question
            </button>
          )}
        </div>
      </div>

      {/* Error banners */}
      {listErrMsg && (
        <div className="mb-3 flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
          <div>
            <p className="font-semibold">Could not load questions</p>
            <p className="mt-0.5">{listErrMsg}</p>
          </div>
        </div>
      )}
      {(reorderErrMsg || createErrMsg) && (
        <div className="mb-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-2 text-xs font-semibold text-amber-800">
          {reorderErrMsg ?? createErrMsg}
        </div>
      )}

      {/* Score calculator — for midterms show proportional scoring info; SAT shows weighted points */}
      {!isLoading && questions.length > 0 && (() => {
        if (examKind === "MIDTERM") {
          const is800 = scoringScale === "SCALE_800";
          return (
            <div className="mb-4 flex items-center gap-3 rounded-2xl border border-primary/20 bg-primary/5 px-4 py-3">
              <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary/10">
                <span className="text-sm font-black text-primary">{is800 ? "Σ" : "%"}</span>
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-xs font-bold uppercase tracking-widest text-primary/70">
                  Midterm scoring · {is800 ? "800-point (SAT scaled)" : "100-point (percentage)"}
                </p>
                <p className="text-sm font-bold text-foreground leading-tight">
                  {questions.length} question{questions.length !== 1 ? "s" : ""} ·{" "}
                  <span className="text-muted-foreground font-normal">
                    {is800
                      ? `${totalScore} pts → SAT 200–800 curve`
                      : `score = correct ÷ ${questions.length} × 100`}
                  </span>
                </p>
              </div>
              <div className="shrink-0 text-right">
                <p className="text-[10px] font-bold uppercase tracking-widest text-primary/60">Max</p>
                <p className="text-lg font-black tabular-nums text-primary leading-tight">{is800 ? 800 : 100}</p>
              </div>
            </div>
          );
        }
        const moduleCap = isSat && sectionSubject
          ? SAT_MODULE_SCORE_CAP[sectionSubject as SatSubject]?.[moduleOrderNum as 1 | 2] ?? null
          : null;
        const remainingPts = moduleCap !== null ? Math.max(0, moduleCap - totalScore) : null;
        return (
          <div className="mb-4 flex items-center gap-3 rounded-2xl border border-primary/20 bg-primary/5 px-4 py-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary/10">
              <span className="text-sm font-black text-primary">Σ</span>
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-xs font-bold uppercase tracking-widest text-primary/70">Module points</p>
              <p className="text-lg font-black tabular-nums text-primary leading-tight">
                {totalScore}
                {moduleCap !== null && (
                  <span className="text-sm font-bold text-muted-foreground"> / {moduleCap}</span>
                )}
              </p>
            </div>
            {remainingPts !== null && remainingPts > 0 && (
              <div className="shrink-0 text-right">
                <p className="text-[10px] font-bold uppercase tracking-widest text-amber-600">Remaining</p>
                <p className="text-lg font-black tabular-nums text-amber-600 leading-tight">
                  +{remainingPts}
                  <span className="ml-1 text-[10px] font-semibold">pts</span>
                </p>
              </div>
            )}
            {remainingPts !== null && remainingPts <= 0 && (
              <div className="shrink-0 text-right">
                <p className="text-[10px] font-bold uppercase tracking-widest text-emerald-600">✓ Complete</p>
              </div>
            )}
          </div>
        );
      })()}

      {/* SAT module health panel */}
      {isSat && !isLoading && (
        <div className="mb-4 rounded-2xl border border-border bg-card px-4 py-3 space-y-2">
          {/* Progress row */}
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2 min-w-0">
              <p className="text-xs font-bold text-muted-foreground uppercase tracking-widest shrink-0">
                {sectionSubject ? SAT_SUBJECT_LABEL[sectionSubject as keyof typeof SAT_SUBJECT_LABEL] ?? sectionSubject : "Section"} · {moduleOrder ?? `Module ${moduleOrderNum}`}
              </p>
            </div>
            <span
              className={`text-xs font-extrabold tabular-nums shrink-0 ${
                progress.complete
                  ? "text-emerald-600"
                  : progress.over
                  ? "text-red-600"
                  : "text-foreground"
              }`}
            >
              {progress.label}
              {progress.required !== null && " questions"}
            </span>
          </div>

          {/* Progress bar */}
          {progress.required !== null && (
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-2">
              <div
                className={`h-full rounded-full transition-all ${
                  progress.complete
                    ? "bg-emerald-500"
                    : progress.over
                    ? "bg-red-500"
                    : "bg-primary"
                }`}
                style={{ width: `${Math.min((progress.fraction ?? 0) * 100, 100)}%` }}
              />
            </div>
          )}

          {/* Count violation */}
          {progress.required !== null && !progress.complete && (
            <p className="text-[11px] font-semibold text-muted-foreground">
              {progress.over
                ? `${progress.current - (progress.required ?? 0)} question(s) over the required ${progress.required}. Remove extras before publishing.`
                : `${(progress.required ?? 0) - progress.current} more question(s) needed to reach the required ${progress.required}.`}
            </p>
          )}

          {/* Type mismatch warning */}
          {typeMismatchIds.size > 0 && (
            <div className="flex items-start gap-1.5 rounded-lg border border-amber-200 bg-amber-50 px-2.5 py-2">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-600" />
              <p className="text-[11px] font-semibold leading-snug text-amber-800">
                {typeMismatchIds.size} question{typeMismatchIds.size !== 1 ? "s have" : " has"} the wrong type for this{" "}
                {sectionSubject === "MATH" ? "Mathematics" : "Reading & Writing"} module.
                Allowed types: {allowedTypesForSubject.join(", ")}.
              </p>
            </div>
          )}

          {/* All-good state */}
          {progress.complete && typeMismatchIds.size === 0 && (
            <div className="flex items-center gap-1.5">
              <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
              <p className="text-[11px] font-semibold text-emerald-700">
                Module is structurally valid — ready to publish.
              </p>
            </div>
          )}
        </div>
      )}

      {/* Split panel */}
      {isLoading ? (
        <StudioSpinner size="lg" center />
      ) : (
        <div className="flex min-h-0 flex-1 gap-5">
          {/* Left: draggable question list */}
          <div className="flex w-72 shrink-0 flex-col gap-2 overflow-y-auto rounded-2xl border border-border bg-card p-3">
            {orderedQuestions.length === 0 ? (
              <div className="flex flex-1 flex-col items-center justify-center gap-3 py-12 text-center">
                <p className="text-sm font-semibold text-foreground">No questions yet</p>
                <p className="text-xs text-muted-foreground">
                  Click &ldquo;Add question&rdquo; to create the first one.
                </p>
              </div>
            ) : (
              <DndContext
                sensors={sensors}
                collisionDetection={closestCenter}
                onDragStart={handleDragStart}
                onDragEnd={(e) => { void handleDragEnd(e); }}
              >
                <SortableContext
                  items={localOrder}
                  strategy={verticalListSortingStrategy}
                >
                  {orderedQuestions.map((q, i) => (
                    <SortableQRow
                      key={q.id}
                      q={q}
                      index={i}
                      selected={q.id === selectedId}
                      reordering={reorderBulk.isPending}
                      hasTypeMismatch={typeMismatchIds.has(q.id)}
                      examKind={examKind}
                      onSelect={() => setSelectedId(q.id)}
                    />
                  ))}
                </SortableContext>

                {/* Drag overlay — floats under cursor */}
                <DragOverlay dropAnimation={null}>
                  {activeQ ? (
                    <DragGhostRow q={activeQ} index={activeIndex} />
                  ) : null}
                </DragOverlay>
              </DndContext>
            )}

            {/* Reorder in-progress indicator */}
            {reorderBulk.isPending && (
              <div className="flex items-center gap-1.5 rounded-xl bg-surface-2 px-3 py-2 text-xs font-semibold text-muted-foreground">
                <Loader2 className="h-3 w-3 animate-spin" />
                Saving order…
              </div>
            )}
          </div>

          {/* Right: editor */}
          <div className="min-h-0 flex-1 overflow-hidden rounded-2xl border border-border bg-card">
            {selectedQ ? (
              <QuestionEditor
                key={selectedQ.id}
                question={selectedQ}
                testId={testId}
                moduleId={moduleId}
                sectionSubject={sectionSubject}
                examKind={examKind}
                scoringScale={scoringScale}
                onSaved={(updated) => {
                  setSelectedId(updated.id);
                }}
                onDeleted={() => {
                  const remainingIds = orderedQuestions
                    .filter((q) => q.id !== selectedQ.id)
                    .map((q) => q.id);
                  setSelectedId(remainingIds[0] ?? null);
                }}
              />
            ) : (
              <div className="flex h-full flex-col items-center justify-center gap-3 p-12 text-center">
                <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-surface-2">
                  <Plus className="h-6 w-6 text-muted-foreground/40" />
                </div>
                <p className="font-semibold text-foreground">No question selected</p>
                <p className="text-sm text-muted-foreground">
                  Select a question from the list, or add a new one.
                </p>
                <button
                  type="button"
                  disabled={mutationBusy || atCapacity}
                  onClick={() => void handleAdd()}
                  title={atCapacity ? `Module is at capacity (${progress.required} questions max)` : undefined}
                  className="mt-1 inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-2 text-sm font-bold text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
                >
                  <Plus className="h-4 w-4" />
                  Add first question
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
