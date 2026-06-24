"use client";

import AuthGuard from "@/components/AuthGuard";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/cn";
import {
  LayoutDashboard,
  FlaskConical,
  ClipboardCheck,
} from "lucide-react";

/**
 * Builder console navigation (standalone exam-runner repo).
 *
 * Scope is limited to the authoring surfaces that feed the exam runner:
 * practice tests and mock exams. The full monorepo console (question bank,
 * assessments, vocabulary, pastpapers, publish queue, archive) is out of scope.
 *
 * Active-state rules:
 *   - Dashboard: exact match only
 *   - All others: prefix match (covers nested sub-pages)
 */

type NavItem = {
  href: string;
  label: string;
  icon: React.ElementType;
  exact: boolean;
};

// Simulation system (SAT preparation)
const SIMULATION_NAV: NavItem[] = [
  { href: "/builder/practice-tests",  label: "Practice tests", icon: FlaskConical,    exact: false },
  { href: "/builder/mock-exams",      label: "Mock exams",     icon: ClipboardCheck,  exact: false },
];

function isNavActive(pathname: string, href: string, exact: boolean): boolean {
  if (exact) return pathname === href;
  return pathname === href || pathname.startsWith(href + "/");
}

export default function BuilderLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  // Editor pages get a full-screen layout — no sidebar competing for space.
  // Covers: practice test module editor, mock exam module editor.
  const isEditorRoute =
    /^\/builder\/practice-tests\/\d+\/\d+\/\d+/.test(pathname) ||
    /^\/builder\/mock-exams\/\d+\/\d+\/\d+/.test(pathname);

  if (isEditorRoute) {
    return (
      <AuthGuard adminOnly>
        <div className="min-h-screen bg-background text-foreground">{children}</div>
      </AuthGuard>
    );
  }

  function NavLink({ item }: { item: NavItem }) {
    const active = isNavActive(pathname, item.href, item.exact);
    return (
      <Link
        href={item.href}
        className={cn(
          "flex items-center gap-3 rounded-xl px-3 py-2 text-sm font-bold transition-colors",
          active
            ? "bg-primary/10 text-primary"
            : "text-muted-foreground hover:bg-surface-2 hover:text-foreground",
        )}
      >
        <item.icon className="h-4 w-4 shrink-0" aria-hidden />
        {item.label}
      </Link>
    );
  }

  const dashboardActive = isNavActive(pathname, "/builder", true);

  return (
    <AuthGuard adminOnly>
      <div className="app-bg min-h-screen text-foreground">
        <div className="mx-auto w-full max-w-7xl px-4 py-6 md:px-8">
          <div className="grid gap-6 lg:grid-cols-[240px_1fr]">
            {/* Sidebar nav */}
            <aside className="rounded-2xl border border-border bg-card p-4 shadow-sm lg:self-start lg:sticky lg:top-6">
              <div className="mb-4 border-b border-border px-1 pb-4">
                <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-primary">
                  Exam builder
                </p>
                <p className="mt-0.5 text-base font-extrabold text-foreground">MasterSAT</p>
              </div>

              {/* Dashboard */}
              <nav className="flex flex-col gap-0.5 mb-3">
                <Link
                  href="/builder"
                  className={cn(
                    "flex items-center gap-3 rounded-xl px-3 py-2 text-sm font-bold transition-colors",
                    dashboardActive
                      ? "bg-primary/10 text-primary"
                      : "text-muted-foreground hover:bg-surface-2 hover:text-foreground",
                  )}
                >
                  <LayoutDashboard className="h-4 w-4 shrink-0" aria-hidden />
                  Dashboard
                </Link>
              </nav>

              {/* Simulation system */}
              <div className="mb-3">
                <p className="mb-1 px-3 text-[9px] font-black uppercase tracking-[0.15em] text-muted-foreground/60">
                  Simulation
                </p>
                <nav className="flex flex-col gap-0.5">
                  {SIMULATION_NAV.map((item) => (
                    <NavLink key={item.href} item={item} />
                  ))}
                </nav>
              </div>
            </aside>

            {/* Main content area */}
            <main className="min-w-0 min-h-[600px]">{children}</main>
          </div>
        </div>
      </div>
    </AuthGuard>
  );
}
