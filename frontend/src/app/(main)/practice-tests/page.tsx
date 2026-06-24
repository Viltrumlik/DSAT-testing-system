"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { examsStudentApi } from "@/features/examsStudent/api";
import { FlaskConical, ChevronRight, BookOpen, Calculator } from "lucide-react";
import { Card, CardContent, Badge, EmptyState, Alert, Skeleton } from "@/components/ui";

type PracticeTestPackSection = {
  id: number;
  title: string;
  subject: string;
  module_count: number;
};

type PracticeTestPack = {
  id: number;
  title: string;
  description: string;
  is_published: boolean;
  sections: PracticeTestPackSection[];
  created_at: string;
};

function subjectLabel(subject: string): string {
  if (subject === "READING_WRITING") return "Reading & Writing";
  if (subject === "MATH") return "Mathematics";
  return subject;
}

export default function PracticeTestsListPage() {
  const [packs, setPacks] = useState<PracticeTestPack[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const data = await examsStudentApi.getPracticeTestPacksStudent();
        if (!cancelled) setPacks(data as PracticeTestPack[]);
      } catch {
        if (!cancelled) setError("Could not load practice tests.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6 pb-12">
      <div>
        <p className="ds-overline text-primary">Practice</p>
        <h1 className="ds-h1 mt-1">Practice tests</h1>
        <p className="ds-small mt-1">Untimed practice — start any section in any order.</p>
      </div>

      {loading ? (
        <div className="grid gap-4 sm:grid-cols-2">
          {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-36 rounded-2xl" />)}
        </div>
      ) : error ? (
        <Alert tone="danger" title={error}>Please refresh to try again.</Alert>
      ) : packs.length === 0 ? (
        <EmptyState
          icon={FlaskConical}
          title="No practice tests yet"
          description="Practice test packs appear here once your teacher publishes them."
        />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          {packs.map((pack) => (
            <Link key={pack.id} href={`/practice-tests/${pack.id}`} className="ds-ring block rounded-2xl">
              <Card variant="interactive" className="h-full">
                <CardContent className="flex h-full flex-col gap-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <h3 className="ds-h4 truncate">{pack.title || `Practice test #${pack.id}`}</h3>
                      {pack.description ? <p className="mt-1 line-clamp-2 text-[13px] text-muted-foreground">{pack.description}</p> : null}
                    </div>
                    <ChevronRight className="h-5 w-5 shrink-0 text-label-foreground" />
                  </div>
                  <div className="mt-auto flex flex-wrap gap-1.5">
                    {pack.sections.map((s) => {
                      const isRW = s.subject === "READING_WRITING";
                      return (
                        <Badge key={s.id} variant={isRW ? "info" : "success"}>
                          {isRW ? <BookOpen className="h-3 w-3" /> : <Calculator className="h-3 w-3" />}
                          {subjectLabel(s.subject)}
                        </Badge>
                      );
                    })}
                  </div>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
