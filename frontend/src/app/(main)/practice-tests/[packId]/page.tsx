"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { examsStudentApi } from "@/features/examsStudent/api";
import { useAuthCriticalGate } from "@/hooks/useAuthCriticalGate";
import { ArrowLeft, BookOpen, Calculator } from "lucide-react";
import { Card, CardContent, Badge, Button, EmptyState, Skeleton } from "@/components/ui";
import { cn } from "@/lib/cn";

type PackSection = {
  id: number;
  title: string;
  subject: string;
  module_count: number;
};

type Pack = {
  id: number;
  title: string;
  description: string;
  sections: PackSection[];
};

type AttemptRow = {
  id: number;
  practice_test: number;
  is_completed: boolean;
  is_expired: boolean;
  score?: number | null;
};

function isRWSubject(s: string): boolean {
  return s === "READING_WRITING";
}

function subjectLabel(s: string): string {
  if (s === "READING_WRITING") return "Reading & Writing";
  if (s === "MATH") return "Mathematics";
  return s;
}

export default function PracticeTestPackDetailPage() {
  const params = useParams();
  const router = useRouter();
  const packId = Number(Array.isArray(params.packId) ? params.packId[0] : params.packId);
  const { assertCriticalAuth } = useAuthCriticalGate();

  const [pack, setPack] = useState<Pack | null>(null);
  const [attempts, setAttempts] = useState<AttemptRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!Number.isFinite(packId) || packId <= 0) return;
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const [packData, attemptsData] = await Promise.all([
          examsStudentApi.getPracticeTestPackStudent(packId),
          examsStudentApi.getAttempts().catch(() => []),
        ]);
        if (!cancelled) {
          setPack(packData as Pack);
          const ad = attemptsData as unknown;
          const raw = Array.isArray(ad) ? ad
            : Array.isArray((ad as { results?: unknown[] })?.results) ? (ad as { results: AttemptRow[] }).results
            : [];
          setAttempts(raw as AttemptRow[]);
        }
      } catch {
        if (!cancelled) setError("Could not load practice test.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [packId]);

  const handleStart = async (sectionId: number) => {
    if (!assertCriticalAuth()) return;
    setStarting(sectionId);
    try {
      let attempt = attempts.find(
        (a) => a.practice_test === sectionId && !a.is_completed && !a.is_expired,
      );
      if (!attempt) {
        attempt = (await examsStudentApi.startTest(sectionId)) as AttemptRow;
        setAttempts((prev) => [...prev, attempt!]);
      }
      try {
        sessionStorage.setItem(`mastersat.attempt.bootstrap.${attempt.id}`, JSON.stringify(attempt));
      } catch {}
      router.push(`/exam/${attempt.id}`);
    } catch (e) {
      console.error("[practice-test] start section failed", e);
      setStarting(null);
    }
  };

  if (loading) {
    return (
      <div className="mx-auto flex max-w-2xl flex-col gap-4">
        <Skeleton className="h-6 w-40" />
        <Skeleton className="h-10 w-64" />
        {[0, 1].map((i) => <Skeleton key={i} className="h-28 rounded-2xl" />)}
      </div>
    );
  }

  if (!pack) {
    return (
      <div className="mx-auto max-w-xl py-16">
        <EmptyState
          title={error ?? "Practice test not found"}
          description="It may have been unpublished."
          action={<Link href="/practice-tests"><Button variant="secondary">Back to practice tests</Button></Link>}
        />
      </div>
    );
  }

  const sorted = [...pack.sections].sort((a, b) =>
    (isRWSubject(a.subject) ? 0 : 1) - (isRWSubject(b.subject) ? 0 : 1)
  );

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-6 pb-12">
      <Link href="/practice-tests" className="ds-ring inline-flex w-fit items-center gap-1.5 rounded-lg text-sm font-semibold text-muted-foreground transition-colors hover:text-foreground">
        <ArrowLeft className="h-4 w-4" /> Back to practice tests
      </Link>

      <div>
        <h1 className="ds-h1">{pack.title || `Practice test #${pack.id}`}</h1>
        {pack.description ? <p className="ds-lead mt-2">{pack.description}</p> : null}
        <p className="ds-small mt-1">Start any section in any order — no time limit between sections.</p>
      </div>

      {sorted.length === 0 ? (
        <EmptyState compact title="No sections yet" description="Sections appear here once added." />
      ) : (
        <div className="grid gap-4">
          {sorted.map((section) => {
            const rw = isRWSubject(section.subject);
            const Icon = rw ? BookOpen : Calculator;
            const sectionAttempts = attempts.filter((a) => a.practice_test === section.id).sort((a, b) => b.id - a.id);
            const completedAttempt = sectionAttempts.find((a) => a.is_completed);
            const activeAttempt = sectionAttempts.find((a) => !a.is_completed && !a.is_expired);
            const isCompleted = !!completedAttempt;
            const isLoading = starting === section.id;
            const label = isCompleted ? "Retake" : activeAttempt ? "Resume" : "Start";

            return (
              <Card key={section.id}>
                <CardContent className="flex flex-col gap-4">
                  <div className="flex items-start gap-4">
                    <div className={cn("flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl", rw ? "bg-info-soft text-info-foreground" : "bg-success-soft text-success-foreground")}>
                      <Icon className="h-6 w-6" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <h3 className="ds-h4">{subjectLabel(section.subject)}</h3>
                      <p className="mt-0.5 text-[12px] text-muted-foreground">{section.module_count} module{section.module_count !== 1 ? "s" : ""}</p>
                      {isCompleted ? (
                        <span className="mt-1.5 inline-block"><Badge variant="success">Completed{completedAttempt?.score != null ? ` · ${completedAttempt.score}` : ""}</Badge></span>
                      ) : null}
                    </div>
                  </div>
                  <Button
                    fullWidth
                    variant={isCompleted ? "secondary" : "primary"}
                    loading={isLoading}
                    onClick={() => handleStart(section.id)}
                  >
                    {label}
                  </Button>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
