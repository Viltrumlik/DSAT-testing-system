"use client";

/**
 * /builder/mock-exams — Mock Exams hub (Simulation system)
 *
 * Mock Exams are SAT simulation infrastructure — full or partial timed exams
 * authored by staff, with score benchmarking and timing realism.
 *
 * Domain: Pastpaper/Simulation (see DOMAIN_ARCHITECTURE.md § System 2)
 * NOT: homework, assignments, or classroom workflows.
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import { examsAdminApi } from "@/features/examsAdmin/api";
import {
  BookOpen,
  Calculator,
  Calendar,
  CheckCircle2,
  ChevronRight,
  Clock,
  Eye,
  EyeOff,
  FileText,
  Loader2,
  Pencil,
  Plus,
  RefreshCcw,
  Trash2,
  X,
  Zap,
} from "lucide-react";
import { STUDIO_FIELD_LABEL, STUDIO_INPUT } from "@/components/studio/primitives";

// ─── Types ────────────────────────────────────────────────────────────────────

type AdminModule = {
  id: number;
  module_order: number | null;
  time_limit_minutes: number | null;
};

type AdminTestSection = {
  id: number;
  title: string;
  subject: string;
  label: string;
  form_type: string;
  modules: AdminModule[];
};

type AdminMockExam = {
  id: number;
  title: string;
  practice_date: string | null;
  is_active: boolean;
  is_published: boolean;
  published_at: string | null;
  kind: "MOCK_SAT" | "MIDTERM";
  tests: AdminTestSection[];
  publish_ready: boolean;
  publish_block_reason: string;
};

type FormState = {
  title: string;
  practice_date: string;
};

const EMPTY_FORM: FormState = { title: "", practice_date: "" };

// ─── Helpers ──────────────────────────────────────────────────────────────────

function formatDate(s: string | null | undefined): string {
  if (!s) return "—";
  try {
    return new Date(s).toLocaleDateString("en-US", { month: "long", year: "numeric" });
  } catch {
    return s;
  }
}

function subjectLabel(subject: string): string {
  if (subject === "READING_WRITING") return "Reading & Writing";
  if (subject === "MATH") return "Mathematics";
  return subject;
}

function SubjectIcon({ subject }: { subject: string }) {
  if (subject === "MATH") return <Calculator className="h-3.5 w-3.5" />;
  return <BookOpen className="h-3.5 w-3.5" />;
}

function parseError(e: unknown): string {
  const data = (e as { response?: { data?: unknown } })?.response?.data;
  if (!data) return "An error occurred.";
  if (typeof data === "string") return data;
  if (typeof data === "object" && data !== null) {
    const d = data as Record<string, unknown>;
    if (typeof d.detail === "string") return d.detail;
    const parts = Object.entries(d)
      .map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(" ") : String(v)}`)
      .join(" ");
    return parts || "An error occurred.";
  }
  return "An error occurred.";
}

const FL = STUDIO_FIELD_LABEL;
const SI = STUDIO_INPUT;

// ─── Modal ────────────────────────────────────────────────────────────────────

function MockExamModal({
  open,
  title,
  initial,
  saving,
  error,
  onSubmit,
  onClose,
}: {
  open: boolean;
  title: string;
  initial: FormState;
  saving: boolean;
  error: string | null;
  onSubmit: (f: FormState) => void;
  onClose: () => void;
}) {
  const [form, setForm] = useState<FormState>(initial);

  useEffect(() => {
    if (open) setForm(initial);
  }, [open, initial]);

  if (!open) return null;

  const set =
    (k: keyof FormState) =>
    (e: React.ChangeEvent<HTMLInputElement>) =>
      setForm((p) => ({ ...p, [k]: e.target.value }));

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative z-10 w-full max-w-md rounded-2xl border border-border bg-card p-6 shadow-xl">
        <div className="mb-5 flex items-center justify-between">
          <h2 className="text-base font-extrabold text-foreground">{title}</h2>
          <button type="button" onClick={onClose} className="rounded-lg p-1 hover:bg-surface-2">
            <X className="h-4 w-4 text-muted-foreground" />
          </button>
        </div>

        {error && (
          <div className="mb-4 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm font-semibold text-red-700">
            {error}
          </div>
        )}

        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            onSubmit(form);
          }}
        >
          <div>
            <label className={FL}>Title</label>
            <input
              value={form.title}
              onChange={set("title")}
              required
              placeholder="e.g. SAT Mock Exam — April 2025"
              className={SI}
            />
          </div>

          <div>
            <label className={FL}>Practice date</label>
            <input
              type="date"
              value={form.practice_date}
              onChange={set("practice_date")}
              className={SI}
            />
          </div>

          <div className="flex gap-2 pt-1">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 rounded-xl border border-border bg-card px-4 py-2.5 text-sm font-bold text-foreground hover:bg-surface-2 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving || !form.title.trim()}
              className="flex flex-1 items-center justify-center gap-2 rounded-xl bg-primary px-4 py-2.5 text-sm font-bold text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
            >
              {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              {saving ? "Saving…" : "Save"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ─── Exam row ─────────────────────────────────────────────────────────────────

function ExamRow({
  exam,
  onEdit,
  onDelete,
  onAddSection,
  onPublish,
  onUnpublish,
  addingSection,
  publishing,
}: {
  exam: AdminMockExam;
  onEdit: () => void;
  onDelete: () => void;
  onAddSection: (subject: "READING_WRITING" | "MATH") => void;
  onPublish: () => void;
  onUnpublish: () => void;
  addingSection: boolean;
  publishing: boolean;
}) {
  const [confirmDelete, setConfirmDelete] = useState(false);

  const rwTest = exam.tests.find((t) => t.subject === "READING_WRITING");
  const mathTest = exam.tests.find((t) => t.subject === "MATH");

  const statusColors = exam.is_published
    ? "bg-emerald-100 text-emerald-800"
    : exam.publish_ready
    ? "bg-amber-100 text-amber-800"
    : "bg-surface-2 text-muted-foreground";

  const statusLabel = exam.is_published
    ? "Published"
    : exam.publish_ready
    ? "Ready to publish"
    : "Draft";

  return (
    <div className="rounded-2xl border border-border bg-card p-5 shadow-sm">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-extrabold text-foreground">{exam.title || `Mock Exam #${exam.id}`}</h3>
            <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide ${statusColors}`}>
              {statusLabel}
            </span>
          </div>
          <p className="mt-1 flex items-center gap-1.5 text-xs text-muted-foreground">
            <Calendar className="h-3 w-3 shrink-0" />
            {formatDate(exam.practice_date)}
            <span className="text-muted-foreground/40">·</span>
            <span>{exam.tests.length} section{exam.tests.length !== 1 ? "s" : ""}</span>
          </p>
        </div>

        {/* Action bar */}
        <div className="flex shrink-0 flex-wrap items-center gap-1.5">
          {/* Publish / Unpublish */}
          {exam.is_published ? (
            <button
              type="button"
              onClick={onUnpublish}
              disabled={publishing}
              className="inline-flex items-center gap-1.5 rounded-xl border border-amber-200 bg-amber-50 px-3 py-1.5 text-xs font-bold text-amber-700 hover:bg-amber-100 disabled:opacity-50 transition-colors"
            >
              {publishing ? <Loader2 className="h-3 w-3 animate-spin" /> : <EyeOff className="h-3 w-3" />}
              Unpublish
            </button>
          ) : (
            <button
              type="button"
              onClick={onPublish}
              disabled={!exam.publish_ready || publishing}
              title={!exam.publish_ready ? exam.publish_block_reason : "Publish this mock exam"}
              className="inline-flex items-center gap-1.5 rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-xs font-bold text-emerald-700 hover:bg-emerald-100 disabled:opacity-50 transition-colors"
            >
              {publishing ? <Loader2 className="h-3 w-3 animate-spin" /> : <Eye className="h-3 w-3" />}
              Publish
            </button>
          )}

          <button
            type="button"
            onClick={onEdit}
            className="inline-flex items-center gap-1.5 rounded-xl border border-border bg-card px-3 py-1.5 text-xs font-bold text-foreground hover:bg-surface-2 transition-colors"
          >
            <Pencil className="h-3 w-3" />
            Edit
          </button>

          {confirmDelete ? (
            <div className="flex items-center gap-1.5">
              <button
                type="button"
                onClick={onDelete}
                className="rounded-xl bg-red-600 px-3 py-1.5 text-xs font-bold text-white hover:bg-red-700 transition-colors"
              >
                Confirm delete
              </button>
              <button
                type="button"
                onClick={() => setConfirmDelete(false)}
                className="rounded-xl border border-border bg-card px-3 py-1.5 text-xs font-bold text-foreground hover:bg-surface-2"
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
              <Trash2 className="h-3 w-3" />
              Delete
            </button>
          )}
        </div>
      </div>

      {/* Publish block reason */}
      {!exam.is_published && !exam.publish_ready && exam.publish_block_reason && (
        <div className="mt-3 flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2">
          <Zap className="h-3.5 w-3.5 shrink-0 text-amber-600 mt-0.5" />
          <p className="text-xs text-amber-800">{exam.publish_block_reason}</p>
        </div>
      )}

      {/* Sections */}
      {exam.tests.length > 0 && (
        <div className="mt-4 space-y-2">
          {exam.tests.map((test) => {
            const isRW = test.subject === "READING_WRITING";
            const modules = test.modules ?? [];
            return (
              <div key={test.id}>
                <div className="mb-1.5 flex items-center gap-2 px-1">
                  <div
                    className={`rounded-md p-1 ${isRW ? "bg-primary/10 text-primary" : "bg-emerald-100 text-emerald-700"}`}
                  >
                    <SubjectIcon subject={test.subject} />
                  </div>
                  <span className="text-xs font-bold text-foreground">{subjectLabel(test.subject)}</span>
                  <span className="text-[10px] text-muted-foreground">
                    {modules.length} module{modules.length !== 1 ? "s" : ""}
                  </span>
                </div>

                {modules.length === 0 ? (
                  <p className="rounded-xl border border-dashed border-border px-4 py-2.5 text-xs text-muted-foreground italic">
                    No modules yet — questions will appear here after auto-creation.
                  </p>
                ) : (
                  <div className="grid gap-1.5 sm:grid-cols-2">
                    {modules.map((mod) => (
                      <Link
                        key={mod.id}
                        href={`/builder/mock-exams/${exam.id}/${test.id}/${mod.id}`}
                        className={`group flex items-center gap-3 rounded-xl border px-4 py-3 transition-colors hover:border-primary/30 hover:bg-primary/5 ${
                          isRW ? "border-primary/20 bg-primary/5" : "border-emerald-200 bg-emerald-50/50"
                        }`}
                      >
                        <div className="min-w-0 flex-1">
                          <p className="text-xs font-extrabold text-foreground">
                            {mod.module_order != null ? `Module ${mod.module_order}` : `Module #${mod.id}`}
                          </p>
                          {mod.time_limit_minutes != null && (
                            <p className="flex items-center gap-1 text-[10px] text-muted-foreground mt-0.5">
                              <Clock className="h-2.5 w-2.5" />
                              {mod.time_limit_minutes} min
                            </p>
                          )}
                        </div>
                        <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground transition-colors group-hover:text-primary" />
                      </Link>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Add section */}
      <div className="mt-3 flex flex-wrap gap-2">
        {!rwTest && (
          <button
            type="button"
            onClick={() => onAddSection("READING_WRITING")}
            disabled={addingSection}
            className="inline-flex items-center gap-1.5 rounded-xl border border-dashed border-primary/40 px-3 py-1.5 text-xs font-semibold text-primary hover:border-primary/70 hover:bg-primary/5 disabled:opacity-50 transition-colors"
          >
            <Plus className="h-3 w-3" />
            Add Reading &amp; Writing
          </button>
        )}
        {!mathTest && (
          <button
            type="button"
            onClick={() => onAddSection("MATH")}
            disabled={addingSection}
            className="inline-flex items-center gap-1.5 rounded-xl border border-dashed border-emerald-400/50 px-3 py-1.5 text-xs font-semibold text-emerald-700 hover:border-emerald-500 hover:bg-emerald-50 disabled:opacity-50 transition-colors"
          >
            <Plus className="h-3 w-3" />
            Add Mathematics
          </button>
        )}
        {rwTest && mathTest && (
          <p className="flex items-center gap-1.5 text-xs text-emerald-700">
            <CheckCircle2 className="h-3.5 w-3.5" />
            Both sections added
          </p>
        )}
      </div>
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function BuilderMockExamsPage() {
  const [exams, setExams] = useState<AdminMockExam[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Modal
  const [modalOpen, setModalOpen] = useState(false);
  const [editingExam, setEditingExam] = useState<AdminMockExam | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  // Per-exam state
  const [addingSectionFor, setAddingSectionFor] = useState<number | null>(null);
  const [publishingId, setPublishingId] = useState<number | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const raw = await examsAdminApi.getMockExams();
      // The admin API returns a plain array; cast to the full shape we know the serializer returns.
      const all = (raw as unknown as AdminMockExam[]).filter((e) => e.kind === "MOCK_SAT");
      setExams(all);
    } catch (e) {
      setError(parseError(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const openCreate = () => {
    setEditingExam(null);
    setSaveError(null);
    setModalOpen(true);
  };

  const openEdit = (exam: AdminMockExam) => {
    setEditingExam(exam);
    setSaveError(null);
    setModalOpen(true);
  };

  const handleSave = async (form: FormState) => {
    setSaving(true);
    setSaveError(null);
    try {
      const payload = {
        title: form.title.trim(),
        practice_date: form.practice_date || null,
        kind: "MOCK_SAT",
      };
      if (editingExam) {
        await examsAdminApi.updateMockExam(editingExam.id, payload);
      } else {
        await examsAdminApi.createMockExam(payload);
      }
      setModalOpen(false);
      await load();
    } catch (e) {
      setSaveError(parseError(e));
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await examsAdminApi.deleteMockExam(id);
      await load();
    } catch (e) {
      setError(parseError(e));
    }
  };

  const handleAddSection = async (examId: number, subject: "READING_WRITING" | "MATH") => {
    setAddingSectionFor(examId);
    try {
      await examsAdminApi.addTestToExam(examId, subject);
      await load();
    } catch (e) {
      setError(parseError(e));
    } finally {
      setAddingSectionFor(null);
    }
  };

  const handlePublish = async (examId: number) => {
    setPublishingId(examId);
    try {
      await examsAdminApi.publishMockExam(examId);
      await load();
    } catch (e) {
      setError(parseError(e));
    } finally {
      setPublishingId(null);
    }
  };

  const handleUnpublish = async (examId: number) => {
    setPublishingId(examId);
    try {
      await examsAdminApi.unpublishMockExam(examId);
      await load();
    } catch (e) {
      setError(parseError(e));
    } finally {
      setPublishingId(null);
    }
  };

  const modalInitial: FormState = editingExam
    ? { title: editingExam.title ?? "", practice_date: editingExam.practice_date ?? "" }
    : EMPTY_FORM;

  const publishedCount = exams.filter((e) => e.is_published).length;
  const draftCount = exams.filter((e) => !e.is_published).length;

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="mb-1 text-[10px] font-bold uppercase tracking-widest text-primary">
            Simulation System
          </p>
          <h1 className="text-xl font-bold text-foreground tracking-tight">Mock Exams</h1>
          <p className="mt-1 text-sm text-muted-foreground max-w-xl">
            Staff-authored timed mock exams for SAT simulation. Each mock contains a Reading &amp;
            Writing section and a Mathematics section. Students experience them as full timed SAT
            conditions — not as homework.
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <button
            type="button"
            onClick={() => void load()}
            disabled={loading}
            className="inline-flex items-center gap-1.5 rounded-xl border border-border bg-card px-3 py-2 text-sm font-bold text-foreground hover:bg-surface-2 disabled:opacity-50 transition-colors"
          >
            <RefreshCcw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </button>
          <button
            type="button"
            onClick={openCreate}
            className="inline-flex items-center gap-1.5 rounded-xl bg-primary px-4 py-2 text-sm font-bold text-primary-foreground hover:bg-primary/90 transition-colors"
          >
            <Plus className="h-4 w-4" />
            New mock exam
          </button>
        </div>
      </div>

      {/* Stats strip */}
      {!loading && exams.length > 0 && (
        <div className="flex flex-wrap gap-3">
          <div className="inline-flex items-center gap-1.5 rounded-xl border border-border bg-card px-3 py-2 text-xs font-semibold text-foreground">
            <FileText className="h-3.5 w-3.5 text-muted-foreground" />
            {exams.length} mock exam{exams.length !== 1 ? "s" : ""}
          </div>
          {publishedCount > 0 && (
            <div className="inline-flex items-center gap-1.5 rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs font-semibold text-emerald-700">
              <Eye className="h-3.5 w-3.5" />
              {publishedCount} published
            </div>
          )}
          {draftCount > 0 && (
            <div className="inline-flex items-center gap-1.5 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-semibold text-amber-700">
              <Pencil className="h-3.5 w-3.5" />
              {draftCount} draft{draftCount !== 1 ? "s" : ""}
            </div>
          )}
        </div>
      )}

      {/* Error banner */}
      {error && (
        <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm font-semibold text-red-700">
          {error}
        </div>
      )}

      {/* Content */}
      {loading ? (
        <div className="flex justify-center py-16">
          <div className="h-10 w-10 animate-spin rounded-full border-4 border-primary border-t-transparent" />
        </div>
      ) : exams.length === 0 ? (
        <div className="rounded-2xl border border-border bg-card p-12 text-center">
          <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-surface-2">
            <FileText className="h-7 w-7 text-muted-foreground/40" />
          </div>
          <p className="font-extrabold text-foreground">No mock exams yet</p>
          <p className="mt-1 mx-auto max-w-xs text-sm text-muted-foreground leading-relaxed">
            Create a mock exam, add Reading &amp; Writing and Mathematics sections, then author
            questions in each module.
          </p>
          <button
            type="button"
            onClick={openCreate}
            className="mt-5 inline-flex items-center gap-2 rounded-xl bg-primary px-5 py-2.5 text-sm font-bold text-primary-foreground hover:bg-primary/90 transition-colors"
          >
            <Plus className="h-4 w-4" />
            New mock exam
          </button>
        </div>
      ) : (
        <div className="space-y-4">
          {exams.map((exam) => (
            <ExamRow
              key={exam.id}
              exam={exam}
              onEdit={() => openEdit(exam)}
              onDelete={() => void handleDelete(exam.id)}
              onAddSection={(subject) => void handleAddSection(exam.id, subject)}
              onPublish={() => void handlePublish(exam.id)}
              onUnpublish={() => void handleUnpublish(exam.id)}
              addingSection={addingSectionFor === exam.id}
              publishing={publishingId === exam.id}
            />
          ))}
        </div>
      )}

      {/* Modal */}
      <MockExamModal
        open={modalOpen}
        title={editingExam ? "Edit mock exam" : "New mock exam"}
        initial={modalInitial}
        saving={saving}
        error={saveError}
        onSubmit={(f) => void handleSave(f)}
        onClose={() => setModalOpen(false)}
      />
    </div>
  );
}
