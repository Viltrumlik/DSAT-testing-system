"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { examsStudentApi } from "@/features/examsStudent/api";
import { ArrowRight, Clock, FileText, Search, Target, Trophy } from "lucide-react";
import { useMe } from "@/hooks/useMe";
import { Card, CardContent, Badge, Button, Input, Select, Stat, ProgressRing, Progress, EmptyState } from "@/components/ui";

type ExamKindFilter = "ALL" | "MOCK_SAT" | "MIDTERM";

type MockExamsListProps = {
  eyebrow?: string;
  title: string;
  description?: string;
  mockQuerySuffix?: string;
  examKindFilter?: ExamKindFilter;
};

const examsPublicApi = examsStudentApi;

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function routeMockId(group: any) {
  return group.mock_exam_id ?? group.id;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function sectionTestIds(group: any): number[] {
  if (Array.isArray(group.section_test_ids)) return group.section_test_ids;
  const tests = group.tests || [];
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return tests.map((t: any) => t.id).filter(Boolean);
}

export default function MockExamsList({
  eyebrow = "Student portal",
  title,
  description,
  mockQuerySuffix = "",
  examKindFilter = "ALL",
}: MockExamsListProps) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [mockExams, setMockExams] = useState<any[]>([]);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [attempts, setAttempts] = useState<any[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [dateFilter, setDateFilter] = useState<string>("");
  const router = useRouter();
  const { isAuthenticated } = useMe();
  const isLoggedIn = isAuthenticated;

  useEffect(() => {
    const fetchData = async () => {
      try {
        const mockBundle = await examsPublicApi.getMockExams();
        setMockExams(mockBundle.items);
        if (isLoggedIn) {
          const attemptsBundle = await examsPublicApi.getAttempts();
          setAttempts(attemptsBundle.items);
        }
      } catch (err) {
        console.error(err);
      }
    };
    void fetchData();
  }, [isLoggedIn]);

  const getAvailableDates = () => {
    const dates = new Set<string>();
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    mockExams.forEach((exam: any) => {
      if (exam.practice_date) dates.add(exam.practice_date.substring(0, 7));
    });
    return Array.from(dates).sort().reverse();
  };

  const formatDateLabel = (yearMonth: string) => {
    const [year, month] = yearMonth.split("-");
    return new Date(parseInt(year, 10), parseInt(month, 10) - 1).toLocaleDateString("en-US", { month: "long", year: "numeric" });
  };

  const groupedExams = useMemo(() => {
    if (examKindFilter === "ALL") return mockExams;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    return (mockExams || []).filter((g: any) => {
      if (examKindFilter === "MOCK_SAT") return g.kind !== "MIDTERM";
      if (examKindFilter === "MIDTERM") return g.kind === "MIDTERM";
      return true;
    });
  }, [mockExams, examKindFilter]);

  const formatDate = (dateStr: string) => {
    if (!dateStr) return "No date";
    try {
      return new Date(dateStr).toLocaleDateString("en-US", { day: "numeric", month: "long", year: "numeric" });
    } catch {
      return dateStr;
    }
  };

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const progressForGroup = (group: any) => {
    const ids = sectionTestIds(group);
    if (ids.length === 0) return 0;
    const done = ids.filter((tid) =>
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      attempts.some((a) => a.practice_test === tid && a.is_completed)
    ).length;
    return Math.round((done / ids.length) * 100);
  };

  const filtered = groupedExams
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    .filter((group: any) =>
      (group.title || "").toLowerCase().includes(searchQuery.toLowerCase()) ||
      (group.practice_date && group.practice_date.includes(searchQuery))
    )
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    .filter((group: any) =>
      !dateFilter || (group.practice_date && group.practice_date.startsWith(dateFilter))
    );

  const totalMocks = groupedExams.length;
  const completedMocks = groupedExams.filter((g) => progressForGroup(g) === 100).length;
  const inProgressMocks = groupedExams.filter((g) => { const p = progressForGroup(g); return p > 0 && p < 100; }).length;
  const avgProgress = totalMocks > 0 ? Math.round(groupedExams.reduce((s, g) => s + progressForGroup(g), 0) / totalMocks) : 0;

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6 pb-12">
      <div>
        <p className="ds-overline text-primary">{eyebrow}</p>
        <h1 className="ds-h1 mt-1">{title}</h1>
        {description ? <p className="ds-lead mt-1.5 max-w-3xl">{description}</p> : null}
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Stat label="Total" value={totalMocks} icon={FileText} />
        <Stat label="Completed" value={completedMocks} icon={Trophy} />
        <Stat label="In progress" value={inProgressMocks} icon={Clock} />
        <Card><CardContent className="flex items-center gap-4">
          <ProgressRing value={avgProgress} size={48} strokeWidth={5} color={avgProgress >= 80 ? "text-success" : "text-primary"} />
          <div><p className="ds-overline">Avg progress</p><p className="ds-num text-xl font-extrabold text-foreground">{avgProgress}%</p></div>
        </CardContent></Card>
      </div>

      {/* Filters */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="sm:w-56">
          <Select value={dateFilter} onChange={(e) => setDateFilter(e.target.value)} aria-label="Filter by date">
            <option value="">All dates</option>
            {getAvailableDates().map((dateStr) => (
              <option key={dateStr} value={dateStr}>{formatDateLabel(dateStr)}</option>
            ))}
          </Select>
        </div>
        <div className="sm:w-80">
          <Input
            placeholder="Search exams…"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            leftIcon={<Search />}
          />
        </div>
      </div>

      {/* Cards */}
      {groupedExams.length === 0 ? (
        <EmptyState icon={Target} title="No exams yet" description="These appear once your instructor publishes them. Practice with past papers first to build up your skills." />
      ) : filtered.length === 0 ? (
        <EmptyState icon={Search} title="No matching exams" description="Try adjusting your search or date filter." action={<Button variant="secondary" onClick={() => { setSearchQuery(""); setDateFilter(""); }}>Clear filters</Button>} />
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {filtered.map((group) => {
            const pct = progressForGroup(group);
            const mid = routeMockId(group);
            const completed = pct === 100;
            return (
              <Card key={group.id ?? mid} variant="interactive" className="flex flex-col">
                <CardContent className="flex flex-1 flex-col gap-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <Badge variant={group.kind === "MIDTERM" ? "warning" : "primary"}>{group.kind === "MIDTERM" ? "Midterm" : "Timed SAT mock"}</Badge>
                      <p className="mt-1.5 text-[12px] font-semibold text-muted-foreground">{formatDate(group.practice_date)}</p>
                    </div>
                    <ProgressRing value={pct} size={42} strokeWidth={4} color={completed ? "text-success" : "text-primary"} showLabel={false}>
                      <span className="ds-num text-[10px] font-bold text-foreground">{pct}%</span>
                    </ProgressRing>
                  </div>
                  <h3 className="ds-h4 leading-snug">{group.title}</h3>
                  {completed ? <Badge variant="success"><Trophy className="h-3 w-3" /> Completed</Badge> : null}
                  <Progress value={pct} tone={completed ? "success" : "primary"} size="sm" className="mt-auto" />
                  <Button
                    fullWidth
                    variant={completed ? "secondary" : "primary"}
                    rightIcon={<ArrowRight />}
                    onClick={() => {
                      if (!isLoggedIn) { router.push("/login"); return; }
                      router.push(`/mock/${mid}${mockQuerySuffix}`);
                    }}
                  >
                    {completed ? "Review" : "Enter timed mock"}
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
