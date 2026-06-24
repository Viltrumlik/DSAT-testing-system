"use client";

/**
 * /builder/mock-exams/[examId]/[testId]/[moduleId]
 *
 * Question editor for a single module inside a mock exam section.
 * Wraps ModuleQuestionsPanel with mock exam context (breadcrumb, back link).
 *
 * Domain: Simulation system (Mock Exams)
 */

import { Suspense, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import ModuleQuestionsPanel from "@/features/questionsAdmin/ModuleQuestionsPanel";
import { examsAdminApi } from "@/features/examsAdmin/api";

type AdminModule = { id: number; module_order: number | null; time_limit_minutes: number | null };
type AdminTestSection = { id: number; title: string; subject: string; modules: AdminModule[] };
type AdminMockExam = {
  id: number;
  title: string;
  kind: string;
  midterm_scoring_scale?: "SCALE_100" | "SCALE_800";
  tests: AdminTestSection[];
};

function MockExamModuleEditor({
  examId,
  testId,
  moduleId,
}: {
  examId: number;
  testId: number;
  moduleId: number;
}) {
  const [exam, setExam] = useState<AdminMockExam | null>(null);

  // Load exam context for breadcrumb enrichment (non-blocking)
  useEffect(() => {
    let cancelled = false;
    examsAdminApi.getMockExams().then((result) => {
      if (cancelled) return;
      const found = (result as unknown as AdminMockExam[]).find((e) => e.id === examId) ?? null;
      setExam(found);
    });
    return () => {
      cancelled = true;
    };
  }, [examId]);

  const section = exam?.tests.find((t) => t.id === testId) ?? null;
  const module = section?.modules?.find((m) => m.id === moduleId) ?? null;

  const subjectLabel =
    section?.subject === "MATH"
      ? "Mathematics"
      : section?.subject === "READING_WRITING"
      ? "Reading & Writing"
      : null;

  const moduleLabel =
    module?.module_order != null ? `Module ${module.module_order}` : `Module #${moduleId}`;

  return (
    <div className="flex h-[calc(100vh-4rem)] flex-col px-4 py-5 md:px-8">
      <ModuleQuestionsPanel
        testId={testId}
        moduleId={moduleId}
        packTitle={exam?.title ?? undefined}
        sectionSubject={section?.subject ?? undefined}
        moduleOrder={moduleLabel}
        backHref={`/builder/mock-exams`}
        backLabel="Mock exams"
        examKind={exam?.kind ?? undefined}
        scoringScale={exam?.midterm_scoring_scale ?? undefined}
      />
    </div>
  );
}

export default function BuilderMockExamModulePage() {
  const params = useParams();

  const examId = Number(Array.isArray(params.examId) ? params.examId[0] : params.examId);
  const testId = Number(Array.isArray(params.testId) ? params.testId[0] : params.testId);
  const moduleId = Number(
    Array.isArray(params.moduleId) ? params.moduleId[0] : params.moduleId,
  );

  if (
    !Number.isFinite(examId) || examId <= 0 ||
    !Number.isFinite(testId) || testId <= 0 ||
    !Number.isFinite(moduleId) || moduleId <= 0
  ) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center p-8">
        <div className="text-center">
          <p className="font-semibold text-foreground">Invalid route parameters.</p>
          <p className="mt-1 text-sm text-muted-foreground">
            Expected{" "}
            <code className="rounded bg-muted px-1">
              /builder/mock-exams/[examId]/[testId]/[moduleId]
            </code>
          </p>
        </div>
      </div>
    );
  }

  return (
    <Suspense
      fallback={
        <div className="flex min-h-[40vh] items-center justify-center">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
        </div>
      }
    >
      <MockExamModuleEditor examId={examId} testId={testId} moduleId={moduleId} />
    </Suspense>
  );
}
