import {
  LayoutDashboard,
  LineChart,
  Users,
  ClipboardCheck,
  BookOpen,
  BookOpenCheck,
  ClipboardList,
  FileText,
  Languages,
  UserCircle,
  ClipboardPen,
  Table2,
  School,
  Timer,
  FolderOpen,
  Database,
} from "lucide-react";

export type NavItem = {
  href: string;
  label: string;
  icon: React.ElementType;
  /** Marks a page introduced by the rebuild's gap analysis. */
  isNew?: boolean;
};
/** An empty `section` string renders the items as top-level (no header). */
export type NavSection = { section: string; items: NavItem[] };

/**
 * Student information architecture (see docs/UI_REBUILD_IA.md §4).
 * Dashboard + Analytics are top-level; the rest are grouped. Notifications
 * live in the top-bar bell, not the sidebar.
 */
export const studentNav: NavSection[] = [
  {
    section: "",
    items: [
      { href: "/", label: "Dashboard", icon: LayoutDashboard },
      { href: "/analytics", label: "Analytics", icon: LineChart, isNew: true },
    ],
  },
  {
    section: "Learn",
    items: [
      { href: "/classes", label: "Classes", icon: Users },
      { href: "/assessments", label: "Assessments", icon: ClipboardCheck },
    ],
  },
  {
    section: "Practice",
    items: [
      { href: "/question-bank", label: "Question Bank", icon: Database, isNew: true },
      { href: "/pastpapers", label: "Past papers", icon: BookOpen },
      { href: "/practice-tests", label: "Practice tests", icon: BookOpenCheck },
      { href: "/vocabulary", label: "Vocabulary", icon: Languages },
    ],
  },
  {
    section: "Simulation",
    items: [
      { href: "/mock-exam", label: "Timed mock", icon: ClipboardList },
      { href: "/midterm", label: "Midterm", icon: FileText },
    ],
  },
  {
    section: "Account",
    items: [
      { href: "/profile", label: "Profile", icon: UserCircle },
      // Settings is a planned future page — not linked until built (no dead-ends).
    ],
  },
];

/** Teacher information architecture (see docs/UI_REBUILD_IA.md §5). */
export const teacherNav: NavSection[] = [
  {
    section: "",
    items: [
      { href: "/teacher", label: "Dashboard", icon: LayoutDashboard },
      { href: "/teacher/analytics", label: "Analytics", icon: LineChart, isNew: true },
    ],
  },
  {
    section: "Classroom",
    items: [
      { href: "/teacher/classrooms", label: "Classrooms", icon: School },
      { href: "/teacher/midterms", label: "Midterms", icon: Timer },
      { href: "/teacher/materials", label: "Materials", icon: FolderOpen },
      { href: "/teacher/students", label: "Students", icon: Users },
    ],
  },
  {
    section: "Grading",
    items: [
      { href: "/teacher/homework", label: "Homework", icon: ClipboardList },
      { href: "/teacher/grading", label: "Grading", icon: ClipboardPen, isNew: true },
      { href: "/teacher/gradebook", label: "Gradebook", icon: Table2, isNew: true },
    ],
  },
];

export function flattenNav(nav: NavSection[]): NavItem[] {
  return nav.flatMap((s) => s.items);
}

export function isNavItemActive(href: string, pathname: string): boolean {
  if (href === "/" || href === "/teacher") return pathname === href;
  return pathname === href || pathname.startsWith(href + "/");
}

export function pageTitleFor(nav: NavSection[], pathname: string, fallback = "MasterSAT"): string {
  const flat = flattenNav(nav);
  const exact = flat.find((n) => n.href === pathname);
  if (exact) return exact.label;
  const match = flat
    .filter((n) => n.href !== "/" && n.href !== "/teacher")
    .find((n) => isNavItemActive(n.href, pathname));
  return match?.label ?? fallback;
}
