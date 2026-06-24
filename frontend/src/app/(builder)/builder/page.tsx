"use client";

import Link from "next/link";
import { ClipboardCheck, FileText, ArrowRight } from "lucide-react";

// Minimal builder landing for the standalone exam-runner repo. The full monorepo
// dashboard (publish queue, question bank, governance state reference) is out of
// scope here — authoring is limited to practice tests + mock exams.

const LINKS = [
  {
    href: "/builder/practice-tests",
    icon: FileText,
    title: "Practice tests",
    cta: "Author tests, modules & questions",
  },
  {
    href: "/builder/mock-exams",
    icon: ClipboardCheck,
    title: "Mock exams",
    cta: "Assemble full mock exams",
  },
];

export default function BuilderDashboardPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold text-foreground tracking-tight">Builder</h1>
        <p className="text-muted-foreground mt-1">Author the tests the exam runner plays.</p>
      </div>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {LINKS.map((link) => (
          <Link
            key={link.href}
            href={link.href}
            className="group flex items-center gap-4 rounded-2xl border border-border bg-card p-4 hover:border-primary/30 hover:bg-primary/5 transition-colors"
          >
            <div className="shrink-0 rounded-xl bg-surface-2 p-3">
              <link.icon className="h-5 w-5 text-muted-foreground group-hover:text-primary transition-colors" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-extrabold text-foreground">{link.title}</p>
              <p className="mt-0.5 text-xs text-muted-foreground">{link.cta}</p>
            </div>
            <ArrowRight className="h-4 w-4 shrink-0 text-muted-foreground" />
          </Link>
        ))}
      </div>
    </div>
  );
}
