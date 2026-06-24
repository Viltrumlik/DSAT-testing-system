"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useParams } from "next/navigation";
import AuthGuard from "@/components/AuthGuard";
import { examsStudentApi } from "@/features/examsStudent/api";
import { pastpaperPackDisplayTitle, singleDisplayTitle } from "@/lib/practiceTestCards";
import { platformSubjectIsReadingWriting } from "@/lib/permissions";
import { ArrowLeft, BookOpen, Calculator, Clock, Eye, Layers, Play } from "lucide-react";
import { useMe } from "@/hooks/useMe";
import { useAuthCriticalGate } from "@/hooks/useAuthCriticalGate";
import { cn } from "@/lib/cn";
import { Card, CardContent, Badge, Button, EmptyState, Spinner } from "@/components/ui";

const examsPublicApi = examsStudentApi;

function PracticeTestDetailInner() {
  const { id } = useParams();
  const testId = Number(id);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [test, setTest] = useState<any>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [attempts, setAttempts] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const router = useRouter();
  const { isAuthenticated } = useMe();
  const { assertCriticalAuth, criticalAuthReady } = useAuthCriticalGate();

  useEffect(() => {
    const run = async () => {
      try {
        setFetchError(null);
        const data = await examsPublicApi.getPracticeTest(testId);
        setTest(data && typeof data === "object" ? data : null);
        if (isAuthenticated) {
          const attemptsData = await examsPublicApi.getAttempts();
          setAttempts(attemptsData.items);
        } else {
          setAttempts([]);
        }
      } catch (e) {
        console.error("[practice-test detail] load failed", { testId, err: e });
        const message = e instanceof Error ? e.message : "Request failed.";
        setFetchError(message);
        setTest(null);
        setAttempts([]);
      } finally {
        setLoading(false);
      }
    };
    run();
  }, [testId, isAuthenticated]);

  const handleStart = async () => {
    if (!assertCriticalAuth()) return;
    setStarting(true);
    try {
      const attempt = await examsPublicApi.startTest(testId);
      setAttempts((prev) => {
        const exists = prev.some((a) => a.id === attempt.id);
        return exists ? prev : [...prev, attempt];
      });
      try {
        sessionStorage.setItem(`mastersat.attempt.bootstrap.${attempt.id}`, JSON.stringify(attempt));
      } catch {}
      router.push(`/exam/${attempt.id}`);
    } catch (e) {
      console.error(e);
      setStarting(false);
    }
  };

  if (loading) {
    return <div className="flex min-h-[50vh] items-center justify-center"><Spinner className="h-8 w-8 text-primary" /></div>;
  }

  if (!test) {
    return (
      <AuthGuard>
        <div className="mx-auto max-w-xl py-16">
          <EmptyState
            title={fetchError ? "Could not load this practice test" : "Practice test not found"}
            description={fetchError || "It may not be assigned to you."}
            action={<Button variant="secondary" onClick={() => router.push("/practice-tests")}>Back to practice tests</Button>}
          />
        </div>
      </AuthGuard>
    );
  }

  const isRW = platformSubjectIsReadingWriting(test.subject);
  const Icon = isRW ? BookOpen : Calculator;
  const label = isRW ? "Reading & Writing" : "Mathematics";
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const modules: any[] = Array.isArray(test.modules) ? test.modules : [];
  const apiTitle = typeof test.title === "string" ? test.title.trim() : "";
  const packTitle = pastpaperPackDisplayTitle(test);
  const cardSubtitle = apiTitle || (packTitle ? `Past paper pack: ${packTitle}` : singleDisplayTitle(test));
  const attempt = attempts.filter((a) => a.practice_test === test.id).sort((a, b) => (b.id || 0) - (a.id || 0))[0];
  const isCompleted = attempt?.is_completed;
  const hasInProgressAttempt = attempt && !attempt.is_completed && !attempt.is_expired;
  const totalMinutes = modules.reduce((acc: number, m) => acc + (m.time_limit_minutes ?? 0), 0);

  return (
    <AuthGuard>
      <div className="mx-auto flex max-w-2xl flex-col gap-6 pb-12">
        <button type="button" onClick={() => router.push("/practice-tests")} className="ds-ring inline-flex w-fit items-center gap-2 rounded-lg text-sm font-semibold text-muted-foreground transition-colors hover:text-foreground">
          <ArrowLeft className="h-4 w-4" /> Back to practice tests
        </button>

        <p className="ds-small max-w-xl">
          Sectional practice — you can pause the timer. For one continuous SAT run with a break and no pause, use <strong className="text-foreground">Mock exam</strong>.
        </p>

        <Card>
          <CardContent className="flex flex-col gap-6">
            {isCompleted ? <span className="w-fit"><Badge variant="success">Completed</Badge></span> : null}

            <div className="flex items-start gap-5">
              <div className={cn("flex h-16 w-16 shrink-0 items-center justify-center rounded-2xl", isRW ? "bg-info-soft text-info-foreground" : "bg-success-soft text-success-foreground")}>
                <Icon className="h-8 w-8" />
              </div>
              <div className="min-w-0">
                <h2 className="ds-h2">{label}</h2>
                <p className="mt-1 text-sm font-semibold text-muted-foreground">{cardSubtitle}</p>
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  {test.label ? <Badge variant="neutral">{test.label}</Badge> : null}
                  <span className="ds-overline">{test.form_type === "US" ? "US form" : "International"} · {modules.length} module{modules.length !== 1 ? "s" : ""} · {totalMinutes} min</span>
                </div>
              </div>
            </div>

            {modules.length > 0 ? (
              <div className="divide-y divide-border overflow-hidden rounded-2xl border border-border">
                {modules.map((m, mIdx) => {
                  const questionCount = m.question_count ?? m.questions?.length ?? null;
                  return (
                    <div key={m.id} className="flex items-center gap-3 px-4 py-3">
                      <div className={cn("flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[11px] font-bold", isRW ? "bg-info-soft text-info-foreground" : "bg-success-soft text-success-foreground")}>{mIdx + 1}</div>
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-bold text-foreground">Module {mIdx + 1}{mIdx > 0 ? <span className="ml-2 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Adaptive</span> : null}</p>
                        {questionCount != null ? <p className="text-[12px] text-muted-foreground">{questionCount} question{questionCount !== 1 ? "s" : ""}</p> : null}
                      </div>
                      <span className="flex shrink-0 items-center gap-1 text-[12px] font-semibold text-muted-foreground"><Clock className="h-3.5 w-3.5" />{m.time_limit_minutes} min</span>
                    </div>
                  );
                })}
                <div className="flex items-center gap-3 bg-surface-2 px-4 py-2.5">
                  <Layers className="h-4 w-4 shrink-0 text-muted-foreground" />
                  <p className="text-[12px] font-semibold text-muted-foreground">Modules run in sequence — the runner continues automatically after each.</p>
                </div>
              </div>
            ) : null}

            {isCompleted ? (
              <Button fullWidth variant="secondary" size="lg" leftIcon={<Eye />} onClick={() => router.push(`/review/${attempt.id}`)}>Review answers</Button>
            ) : (
              <Button fullWidth size="lg" loading={starting} disabled={!criticalAuthReady} leftIcon={<Play className="fill-current" />} onClick={() => void handleStart()}>
                {hasInProgressAttempt ? "Resume" : "Start test"}
              </Button>
            )}
          </CardContent>
        </Card>
      </div>
    </AuthGuard>
  );
}

export default function PracticeTestDetailPage() {
  return (
    <Suspense fallback={<div className="flex min-h-[50vh] items-center justify-center"><Spinner className="h-8 w-8 text-primary" /></div>}>
      <PracticeTestDetailInner />
    </Suspense>
  );
}
