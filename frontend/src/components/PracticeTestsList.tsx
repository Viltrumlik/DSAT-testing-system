"use client";

import { useEffect, useMemo, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { examsStudentApi } from "@/features/examsStudent/api";
import {
  buildHomeworkPastpaperCards,
  formatLineDate,
  isTimedMockSectionRow,
  practiceTestSearchBlob,
  sharedPastpaperPackTitle,
  singleDisplayTitle,
  sortPastpaperSections,
  subjectLabel,
} from "@/lib/practiceTestCards";
import { ArrowRight, BarChart3, BookOpen, CheckCircle2, FileText, RefreshCw, Search, X } from "lucide-react";
import { cn } from "@/lib/cn";
import { useMe } from "@/hooks/useMe";
import { platformSubjectIsMath } from "@/lib/permissions";
import { PageHeader } from "@/components/ui/PageHeader";
import { ProgressRing } from "@/components/ui/ProgressRing";
import { EmptyState } from "@/components/ui/EmptyState";
import { StatCard } from "@/components/ui/StatCard";

type PracticeTestsListProps = {
  eyebrow?: string;
  title: string;
  description?: string;
};

const examsPublicApi = examsStudentApi;

function progressPack(tests: any[], attempts: any[]) {
  if (!tests.length) return 0;
  const done = tests.filter((t) =>
    attempts.some((a) => a.practice_test === t.id && a.is_completed)
  ).length;
  return Math.round((done / tests.length) * 100);
}

function progressSingle(test: any, attempts: any[]) {
  const att = attempts
    .filter((a) => a.practice_test === test.id)
    .sort((a, b) => (b.id || 0) - (a.id || 0))[0];
  if (!att) return 0;
  if (att.is_completed) return 100;
  const modules = test.modules || [];
  const total = modules.length;
  if (!total) return 0;
  const done = Array.isArray(att.completed_modules) ? att.completed_modules.length : 0;
  return Math.min(100, Math.round((done / total) * 100));
}

/* ── Section footer inside pack cards ─────────────────────────────────── */
function PackSectionFooter({
  tests,
  isLoggedIn,
  router,
  attempts,
}: {
  tests: any[];
  isLoggedIn: boolean;
  attempts: any[];
  router: ReturnType<typeof useRouter>;
}) {
  const sorted = sortPastpaperSections(tests);
  return (
    <div className="p-5 pt-0 mt-auto space-y-2">
      {sorted.map((t) => {
        const pct = progressSingle(t, attempts);
        const att = attempts
          .filter((a) => a.practice_test === t.id)
          .sort((a, b) => (b.id || 0) - (a.id || 0))[0];
        const completed = !!att?.is_completed;
        const isMath = platformSubjectIsMath(t.subject);
        return (
          <button
            key={t.id}
            type="button"
            onClick={() => {
              if (!isLoggedIn) { router.push("/login"); return; }
              router.push(`/practice-test/${t.id}`);
            }}
            className="flex w-full items-center gap-3 rounded-xl border border-border bg-surface-2/60 p-3 transition-all hover:border-primary/25 hover:bg-surface-2 text-left group/section"
          >
            <div className={cn(
              "flex h-9 w-9 shrink-0 items-center justify-center rounded-lg",
              isMath
                ? "bg-blue-50 text-blue-600 dark:bg-blue-950/40 dark:text-blue-400"
                : "bg-violet-50 text-violet-600 dark:bg-violet-950/40 dark:text-violet-400",
            )}>
              {isMath ? <BarChart3 className="h-4 w-4" /> : <BookOpen className="h-4 w-4" />}
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-bold text-foreground">{subjectLabel(t.subject)}</p>
              <p className="text-[10px] font-semibold text-muted-foreground">
                {(t.modules?.length ?? 0)} modules
                {completed && <span className="text-emerald-600 dark:text-emerald-400"> · Done</span>}
              </p>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              {pct > 0 && (
                <ProgressRing value={pct} size={28} strokeWidth={3} showLabel={false}
                  color={completed ? "text-emerald-500" : "text-primary"} />
              )}
              <ArrowRight className="h-4 w-4 text-muted-foreground group-hover/section:text-primary transition-colors" />
            </div>
          </button>
        );
      })}
    </div>
  );
}

/* ═══════════════════════════════ MAIN ═══════════════════════════════════ */
export default function PracticeTestsList({
  eyebrow = "Student portal",
  title,
  description,
}: PracticeTestsListProps) {
  const [tests, setTests] = useState<any[]>([]);
  const [attempts, setAttempts] = useState<any[]>([]);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [listRefreshKey, setListRefreshKey] = useState(0);
  const router = useRouter();
  const pathname = usePathname();
  const { isAuthenticated } = useMe();
  const isLoggedIn = isAuthenticated;

  useEffect(() => {
    let cancelled = false;
    const fetchData = async () => {
      try {
        setFetchError(null);
        const bundle = await examsPublicApi.getPracticeTests();
        if (cancelled) return;
        setTests(bundle.items.filter((t) => !isTimedMockSectionRow(t)));
        if (isLoggedIn) {
          const attemptsData = await examsPublicApi.getAttempts();
          if (!cancelled) setAttempts(attemptsData.items);
        } else {
          setAttempts([]);
        }
      } catch (err) {
        console.error("[practice-tests] failed to load catalog or attempts", err);
        if (!cancelled) {
          const message = err instanceof Error ? err.message : "Could not load practice tests.";
          setFetchError(message);
          setTests([]);
          setAttempts([]);
        }
      }
    };
    void fetchData();
    const onVisible = () => {
      if (document.visibilityState === "visible") void fetchData();
    };
    window.addEventListener("visibilitychange", onVisible);
    return () => { cancelled = true; window.removeEventListener("visibilitychange", onVisible); };
  }, [pathname, listRefreshKey, isLoggedIn]);

  const cards = useMemo(() => buildHomeworkPastpaperCards(tests), [tests]);

  const filtered = useMemo(() => {
    const q = searchQuery.toLowerCase().trim();
    if (!q) return cards;
    return cards.filter((c) => {
      if (c.kind === "pastpaper_pack") {
        const blob = `${sharedPastpaperPackTitle(c.tests)} ${formatLineDate(c.tests[0]?.practice_date)} ${c.tests.map((t) => subjectLabel(t.subject)).join(" ")}`.toLowerCase();
        return blob.includes(q);
      }
      return practiceTestSearchBlob(c.test).includes(q);
    });
  }, [cards, searchQuery]);

  /* ── Computed stats ─────────────────────────────────────────────────── */
  const totalTests = tests.length;
  const totalCompleted = attempts.filter((a) => a.is_completed).length;
  const overallProgress = totalTests > 0 ? Math.round((totalCompleted / totalTests) * 100) : 0;
  const inProgress = attempts.filter((a) => !a.is_completed).length;

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 lg:px-6">

      {/* ═══ Header ══════════════════════════════════════════════════════ */}
      <PageHeader
        eyebrow={eyebrow}
        title={title}
        description={description}
        actions={
          <button
            type="button"
            onClick={() => setListRefreshKey((k) => k + 1)}
            className="inline-flex items-center gap-2 rounded-xl border border-border bg-card px-3 py-2.5 text-xs font-bold text-foreground shadow-sm transition-colors hover:border-primary/30 hover:bg-surface-2"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            Refresh
          </button>
        }
      />

      {/* ═══ Error banner ════════════════════════════════════════════════ */}
      {fetchError && (
        <div className="mb-6 rounded-2xl border border-amber-500/40 bg-amber-500/10 px-5 py-4 text-sm" role="alert">
          <p className="font-bold text-amber-900 dark:text-amber-100">Couldn&apos;t load practice tests.</p>
          <p className="mt-1 text-amber-800/80 dark:text-amber-200/80">{fetchError}</p>
          <button
            type="button"
            className="mt-3 rounded-lg bg-foreground px-3 py-1.5 text-xs font-bold text-background"
            onClick={() => setListRefreshKey((k) => k + 1)}
          >
            Try again
          </button>
        </div>
      )}

      {/* ═══ Stats Row ═══════════════════════════════════════════════════ */}
      <div className="grid grid-cols-2 gap-3 mb-6 sm:grid-cols-4">
        <StatCard
          label="Total Tests"
          value={totalTests}
          icon={FileText}
          accent="text-blue-600 bg-blue-50 dark:text-blue-400 dark:bg-blue-950/40"
        />
        <StatCard
          label="Completed"
          value={totalCompleted}
          icon={CheckCircle2}
          accent="text-emerald-600 bg-emerald-50 dark:text-emerald-400 dark:bg-emerald-950/40"
        />
        <StatCard
          label="In Progress"
          value={inProgress}
          icon={RefreshCw}
          accent="text-amber-600 bg-amber-50 dark:text-amber-400 dark:bg-amber-950/40"
        />
        <div className="relative overflow-hidden rounded-2xl border border-border bg-card p-5 flex items-center gap-4">
          <ProgressRing
            value={overallProgress}
            size={48}
            strokeWidth={5}
            color={overallProgress >= 80 ? "text-emerald-500" : "text-primary"}
          />
          <div>
            <p className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">Progress</p>
            <p className="text-xl font-black tabular-nums text-foreground">{overallProgress}%</p>
          </div>
        </div>
      </div>

      {/* ═══ Search ══════════════════════════════════════════════════════ */}
      <div className="group relative mb-8 w-full max-w-md">
        <Search className="absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground transition-colors group-focus-within:text-primary" />
        <input
          type="text"
          placeholder="Search practice packs and tests..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="w-full rounded-xl border border-border bg-card py-3 pl-11 pr-10 text-sm font-medium shadow-sm outline-none transition-all focus:border-primary/40 focus:ring-2 focus:ring-primary/10"
        />
        {searchQuery && (
          <button
            type="button"
            onClick={() => setSearchQuery("")}
            className="absolute right-4 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
            aria-label="Clear search"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>

      {/* ═══ Cards Grid ══════════════════════════════════════════════════ */}
      <div className="grid grid-cols-1 gap-5 md:grid-cols-2 lg:grid-cols-3">
        {filtered.map((c) => {
          if (c.kind === "pastpaper_pack") {
            const pct = progressPack(c.tests, attempts);
            const lineDate = c.pack?.practice_date || c.tests[0]?.practice_date || c.tests[0]?.created_at;
            const heading = (c.pack?.title && String(c.pack.title).trim()) || sharedPastpaperPackTitle(c.tests);
            return (
              <div
                key={`pastpaper-pack-${c.packKey}`}
                className="group flex flex-col overflow-hidden rounded-2xl border border-border bg-card transition-all hover:border-primary/25 hover:shadow-md"
              >
                <div className="p-5 pb-3">
                  <div className="mb-4 flex items-center justify-between">
                    <div>
                      <span className="text-[10px] font-bold uppercase tracking-widest text-primary">Practice Test</span>
                      <p className="text-xs font-semibold text-muted-foreground mt-0.5">{formatLineDate(lineDate)}</p>
                    </div>
                    <div className="flex items-center gap-2">
                      <ProgressRing
                        value={pct}
                        size={36}
                        strokeWidth={3}
                        color={pct >= 100 ? "text-emerald-500" : "text-primary"}
                      >
                        <span className="text-[9px] font-black tabular-nums text-foreground">{pct}%</span>
                      </ProgressRing>
                    </div>
                  </div>
                  <h3 className="text-lg font-extrabold leading-snug tracking-tight text-foreground group-hover:text-primary transition-colors">
                    {heading}
                  </h3>
                  <div className="mt-3 flex items-center gap-2">
                    <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-2">
                      <div
                        className={cn(
                          "h-full rounded-full transition-all duration-700",
                          pct >= 100 ? "bg-emerald-500" : "bg-primary",
                        )}
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  </div>
                </div>
                <PackSectionFooter tests={c.tests} isLoggedIn={isLoggedIn} router={router} attempts={attempts} />
              </div>
            );
          }

          const t = c.test;
          const pct = progressSingle(t, attempts);
          const att = attempts
            .filter((a) => a.practice_test === t.id)
            .sort((a, b) => (b.id || 0) - (a.id || 0))[0];
          const completed = !!att?.is_completed;

          return (
            <div
              key={`single-${t.id}`}
              className="group flex flex-col overflow-hidden rounded-2xl border border-border bg-card transition-all hover:border-primary/25 hover:shadow-md"
            >
              <div className="p-5 pb-3">
                <div className="mb-4 flex items-center justify-between">
                  <div>
                    <span className="text-[10px] font-bold uppercase tracking-widest text-primary">Practice Test</span>
                    <p className="text-xs font-semibold text-muted-foreground mt-0.5">
                      {formatLineDate(t.practice_date || t.created_at)}
                    </p>
                  </div>
                  <ProgressRing
                    value={pct}
                    size={36}
                    strokeWidth={3}
                    color={completed ? "text-emerald-500" : "text-primary"}
                  >
                    <span className="text-[9px] font-black tabular-nums text-foreground">{pct}%</span>
                  </ProgressRing>
                </div>
                <h3 className="text-lg font-extrabold leading-snug tracking-tight text-foreground group-hover:text-primary transition-colors">
                  {singleDisplayTitle(t)}
                </h3>
                {completed && (
                  <span className="mt-2 inline-flex items-center gap-1 rounded-lg bg-emerald-50 px-2 py-0.5 text-[10px] font-bold text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-400">
                    <CheckCircle2 className="h-3 w-3" />
                    Completed
                  </span>
                )}
                <div className="mt-3 flex items-center gap-2">
                  <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-2">
                    <div
                      className={cn(
                        "h-full rounded-full transition-all duration-700",
                        completed ? "bg-emerald-500" : "bg-primary",
                      )}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
              </div>
              <div className="mt-auto p-5 pt-3">
                <button
                  type="button"
                  onClick={() => {
                    if (!isLoggedIn) { router.push("/login"); return; }
                    router.push(`/practice-test/${t.id}`);
                  }}
                  className="flex w-full items-center justify-center gap-2 rounded-xl bg-primary py-3 text-sm font-bold text-primary-foreground hover:bg-primary/90 transition-colors active:scale-[0.98]"
                >
                  {completed ? "Review" : "Start Practice"}
                  <ArrowRight className="h-4 w-4" />
                </button>
              </div>
            </div>
          );
        })}

        {filtered.length === 0 && (
          <div className="col-span-full">
            <EmptyState
              icon={FileText}
              title={searchQuery ? "No matching tests" : "No practice tests yet"}
              description={
                searchQuery
                  ? "Try a different search term or clear the filter."
                  : "Practice tests will appear here once assigned."
              }
              action={
                searchQuery ? (
                  <button
                    type="button"
                    onClick={() => setSearchQuery("")}
                    className="inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-2.5 text-sm font-bold text-primary-foreground"
                  >
                    Clear search
                  </button>
                ) : undefined
              }
            />
          </div>
        )}
      </div>
    </div>
  );
}
