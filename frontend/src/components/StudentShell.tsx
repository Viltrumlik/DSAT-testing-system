"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { authApi } from "@/lib/api";
import { useMe } from "@/hooks/useMe";
import { useTheme } from "next-themes";
import {
  LayoutDashboard,
  BookOpen,
  BookOpenCheck,
  ClipboardCheck,
  ClipboardList,
  FileWarning,
  Users,
  UserCircle,
  Languages,
  LogOut,
  LogIn,
  Sun,
  Moon,
  Menu,
  X,
  Search,
  Zap,
  ChevronLeft,
  ChevronRight,
  Bell,
} from "lucide-react";
import AuthGuard from "@/components/AuthGuard";
import { Badge } from "@/components/ui/Badge";
import { IconButton } from "@/components/ui/IconButton";
import { Tooltip } from "@/components/ui/Tooltip";
import { cn } from "@/lib/cn";

const SIDEBAR_COLLAPSED_KEY = "mastersat.sidebarCollapsed";

// ─── Nav sections — Learning (pedagogical) vs Simulation (SAT-mode) ───────────

type NavItem = { href: string; label: string; icon: React.ElementType };
type NavSection = { section: string; items: NavItem[] };

const navSections: NavSection[] = [
  {
    section: "Learning",
    items: [
      { href: "/", label: "Dashboard", icon: LayoutDashboard },
      { href: "/assessments", label: "Assessments", icon: ClipboardCheck },
      { href: "/midterm", label: "Midterm", icon: FileWarning },
      { href: "/classes", label: "Classes", icon: Users },
    ],
  },
  {
    section: "Simulation",
    items: [
      { href: "/pastpapers", label: "Past papers", icon: BookOpen },
      { href: "/practice-tests", label: "Practice tests", icon: BookOpenCheck },
      { href: "/mock-exam", label: "Timed mock", icon: ClipboardList },
    ],
  },
  {
    section: "Account",
    items: [
      { href: "/profile", label: "Profile", icon: UserCircle },
      { href: "/vocabulary/daily", label: "Vocabulary", icon: Languages },
    ],
  },
];

/** Flat list derived from sections — used for pageTitle / command palette. */
const nav: NavItem[] = navSections.flatMap((s) => s.items);

const quickLinks = [
  { href: "/assessments", label: "Assessments" },
  { href: "/pastpapers", label: "Past papers" },
  { href: "/mock-exam", label: "Mock" },
  { href: "/classes", label: "Classes" },
];

function isNavItemActive(href: string, pathname: string): boolean {
  if (href === "/") return pathname === "/";
  if (href === "/pastpapers") return pathname === "/pastpapers" || pathname.startsWith("/pastpapers/");
  if (href === "/practice-tests") return pathname === "/practice-tests" || pathname.startsWith("/practice-tests/");
  if (href.startsWith("/vocabulary")) return pathname === "/vocabulary" || pathname.startsWith("/vocabulary/");
  return pathname.startsWith(href);
}

function pageTitle(pathname: string): string {
  if (pathname === "/") return "Dashboard";
  if (pathname === "/vocabulary" || pathname.startsWith("/vocabulary/")) return "Vocabulary";
  const item = nav.find((n) => n.href !== "/" && isNavItemActive(n.href, pathname));
  return item?.label ?? "MasterSAT";
}

export default function StudentShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const queryClient = useQueryClient();
  const { isAuthenticated, me, globalInteractionBlockedHard } = useMe();
  const isLoggedIn = isAuthenticated;
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [navQuery, setNavQuery] = useState("");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [headerSearch, setHeaderSearch] = useState("");
  const [headerSearchOpen, setHeaderSearchOpen] = useState(false);
  const [notifOpen, setNotifOpen] = useState(false);
  const [profileImageUrl, setProfileImageUrl] = useState<string | null | undefined>(undefined);
  const [profileAvatarFailed, setProfileAvatarFailed] = useState(false);
  const headerSearchRef = useRef<HTMLDivElement>(null);
  const notifRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    try {
      setSidebarCollapsed(localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === "1");
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    setMounted(true);
  }, [pathname]);

  useEffect(() => {
    if (!isLoggedIn || !me) {
      setProfileImageUrl(undefined);
      setProfileAvatarFailed(false);
      return;
    }
    const m = me as { profile_image_url?: unknown };
    setProfileAvatarFailed(false);
    const url =
      typeof m.profile_image_url === "string" && m.profile_image_url.trim()
        ? m.profile_image_url.trim()
        : null;
    setProfileImageUrl(url);
  }, [isLoggedIn, me, pathname]);

  useEffect(() => {
    setProfileAvatarFailed(false);
  }, [profileImageUrl]);

  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      const t = e.target as Node;
      if (headerSearchRef.current && !headerSearchRef.current.contains(t)) setHeaderSearchOpen(false);
      if (notifRef.current && !notifRef.current.contains(t)) setNotifOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const toggleSidebarCollapsed = () => {
    setSidebarCollapsed((c) => {
      const n = !c;
      try {
        localStorage.setItem(SIDEBAR_COLLAPSED_KEY, n ? "1" : "0");
      } catch {
        /* ignore */
      }
      return n;
    });
  };

  const filteredNavSections = useMemo((): NavSection[] => {
    const q = navQuery.trim().toLowerCase();
    if (!q) return navSections;
    return navSections
      .map((s) => ({ ...s, items: s.items.filter((n) => n.label.toLowerCase().includes(q)) }))
      .filter((s) => s.items.length > 0);
  }, [navQuery]);

  const title = pageTitle(pathname);

  const commandResults = useMemo(() => {
    const q = headerSearch.trim().toLowerCase();
    const fromNav = nav.map((n) => ({ href: n.href, label: n.label }));
    const fromQuick = quickLinks.map((q) => ({ href: q.href, label: q.label }));
    const merged = [...fromNav, ...fromQuick.filter((q) => !fromNav.some((n) => n.href === q.href))];
    if (!q) return merged.slice(0, 6);
    return merged.filter((x) => x.label.toLowerCase().includes(q)).slice(0, 8);
  }, [headerSearch]);

  const navLinkClass = (active: boolean) =>
    cn(
      "group flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-semibold transition-all duration-200",
      sidebarCollapsed && "md:justify-center md:px-2",
      active
        ? "bg-primary/10 text-primary shadow-sm border border-primary/15 font-bold"
        : "text-muted-foreground hover:bg-surface-2 hover:text-foreground border border-transparent",
    );

  return (
    <AuthGuard>
      <div className="app-bg flex min-h-screen flex-col text-foreground transition-colors duration-300 md:h-[100dvh] md:max-h-[100dvh] md:flex-row md:overflow-hidden">
        {/* Mobile drawer overlay */}
        {mobileOpen ? (
          <button
            type="button"
            className="fixed inset-0 z-[90] bg-foreground/20 md:hidden"
            aria-label="Close menu"
            onClick={() => setMobileOpen(false)}
          />
        ) : null}

        {/* Sidebar */}
        <aside
          className={cn(
            "fixed inset-y-0 left-0 z-[100] flex h-[100dvh] w-[min(100%,260px)] shrink-0 flex-col overflow-hidden border-r border-border bg-card transition-[transform,width,padding] duration-200 ease-out md:relative md:z-30 md:h-full md:max-h-full md:min-h-0 md:translate-x-0",
            sidebarCollapsed ? "md:w-[4.25rem] md:px-0" : "md:w-72",
            mobileOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0",
          )}
        >
          <div
            className={cn(
              "border-b border-border",
              sidebarCollapsed
                ? "flex flex-col items-center gap-3 px-3 py-4 md:px-2"
                : "flex flex-row items-center justify-between gap-3 p-4 md:p-5",
            )}
          >
            <div
              className={cn(
                "flex min-w-0 items-center gap-3",
                sidebarCollapsed && "w-full justify-center md:w-auto",
              )}
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src="/images/logo.png"
                alt=""
                className="h-10 w-10 shrink-0 rounded-xl bg-background/80 object-contain p-0.5 ring-1 ring-border"
              />
              <div className={cn("min-w-0 flex-1", sidebarCollapsed && "md:hidden")}>
                <span className="block truncate text-base font-extrabold tracking-tight text-foreground">
                  MasterSAT
                </span>
                <span className="mt-0.5 block text-[10px] font-semibold uppercase tracking-[0.1em] text-primary">
                  Learning OS
                </span>
              </div>
            </div>
            <div
              className={cn(
                "flex shrink-0 items-center gap-1",
                sidebarCollapsed && "w-full justify-center md:w-auto",
              )}
            >
              <IconButton
                variant="ghost"
                size="sm"
                className="hidden md:flex"
                onClick={toggleSidebarCollapsed}
                aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
              >
                {sidebarCollapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
              </IconButton>
              <IconButton
                variant="ghost"
                size="sm"
                className="md:hidden"
                onClick={() => setMobileOpen(false)}
                aria-label="Close navigation"
              >
                <X className="h-4 w-4" />
              </IconButton>
            </div>
          </div>

          <div className={cn("px-4 pt-4 md:px-5", sidebarCollapsed && "md:hidden")}>
            <label className="sr-only" htmlFor="nav-search">
              Filter navigation
            </label>
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-label-foreground" />
              <input
                id="nav-search"
                value={navQuery}
                onChange={(e) => setNavQuery(e.target.value)}
                placeholder="Jump to section…"
                className="ui-input w-full rounded-xl py-2 pl-9 pr-3 text-sm shadow-sm"
              />
            </div>
          </div>

          <nav
            className={cn(
              "flex min-h-0 flex-1 flex-col overflow-y-auto overflow-x-hidden px-3 pb-4 pt-2 md:px-4",
              sidebarCollapsed && "md:items-center md:px-2",
            )}
            aria-label="Main"
          >
            {filteredNavSections.length === 0 ? (
              <p className="px-2 py-6 text-center text-sm text-muted-foreground">No sections match &ldquo;{navQuery}&rdquo;.</p>
            ) : (
              filteredNavSections.map(({ section, items }) => (
                <div key={section} className="mb-3 last:mb-0">
                  {/* Section label — hidden when sidebar is collapsed */}
                  <p className={cn(
                    "mb-1 px-3 text-[9px] font-bold uppercase tracking-widest text-muted-foreground/50",
                    sidebarCollapsed && "md:hidden",
                  )}>
                    {section}
                  </p>
                  <div className="flex flex-col gap-0.5">
                    {items.map(({ href, label, icon: Icon }) => {
                      const active = isNavItemActive(href, pathname);
                      return (
                        <Link
                          key={href}
                          href={href}
                          className={cn(navLinkClass(active), "w-full")}
                          onClick={() => setMobileOpen(false)}
                        >
                          <span
                            className={cn(
                              "flex h-8 w-8 shrink-0 items-center justify-center rounded-md transition-colors",
                              active
                                ? "text-primary"
                                : "text-label-foreground group-hover:text-foreground",
                            )}
                          >
                            <Icon className="h-[18px] w-[18px]" strokeWidth={2} />
                          </span>
                          <span className={cn("leading-snug", sidebarCollapsed && "md:sr-only")}>{label}</span>
                        </Link>
                      );
                    })}
                  </div>
                </div>
              ))
            )}
          </nav>

          <div className={cn("mt-auto border-t border-border p-4", sidebarCollapsed && "md:px-2")}>
            <div className={cn("flex flex-wrap gap-2", sidebarCollapsed && "md:justify-center")}>
              <Badge variant="brand" dot={isLoggedIn}>
                <span className={cn(sidebarCollapsed && "md:sr-only")}>{isLoggedIn ? "Signed in" : "Guest"}</span>
              </Badge>
            </div>
            <p className={cn("ds-caption mt-2 text-[11px]", sidebarCollapsed && "md:hidden")}>
              Tip: use the search box to filter long menus.
            </p>
            {isLoggedIn ? (
              <button
                type="button"
                onClick={() => authApi.logout(queryClient)}
                className={cn(
                  "mt-4 flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm font-semibold text-muted-foreground transition-all hover:bg-surface-2 hover:text-foreground",
                  sidebarCollapsed && "md:justify-center md:px-2",
                )}
              >
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-surface-2 text-label-foreground">
                  <LogOut className="h-[18px] w-[18px]" strokeWidth={2} />
                </span>
                <span className={cn("leading-snug", sidebarCollapsed && "md:sr-only")}>Sign out</span>
              </button>
            ) : null}
          </div>
        </aside>

        <div className="flex min-h-0 min-w-0 flex-1 flex-col md:overflow-hidden">
          {/* Top bar (mobile + desktop) */}
          <header className="sticky top-0 z-40 flex h-[60px] shrink-0 items-center gap-2 border-b border-border bg-card px-2 md:h-[64px] md:gap-3 md:px-6">
            <IconButton
              variant="ghost"
              className="md:hidden"
              aria-label="Open menu"
              onClick={() => setMobileOpen(true)}
            >
              <Menu className="h-5 w-5" />
            </IconButton>

            <div className="flex min-w-0 flex-1 items-center gap-2 md:gap-3">
              <div ref={headerSearchRef} className="relative hidden min-w-0 max-w-xl flex-1 md:block">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-label-foreground" />
                <input
                  value={headerSearch}
                  onChange={(e) => {
                    setHeaderSearch(e.target.value);
                    setHeaderSearchOpen(true);
                  }}
                  onFocus={() => setHeaderSearchOpen(true)}
                  placeholder="Search pages…"
                  className="ui-input w-full rounded-xl border border-border bg-surface-2/80 py-2 pl-9 pr-3 text-sm transition-all"
                  aria-label="Search pages and quick links"
                  aria-expanded={headerSearchOpen}
                  aria-controls="header-search-results"
                />
                {headerSearchOpen && commandResults.length > 0 ? (
                  <ul
                    id="header-search-results"
                    className="absolute left-0 right-0 top-[calc(100%+6px)] z-50 max-h-72 overflow-auto rounded-lg border border-border bg-card py-1 shadow-lg"
                    role="listbox"
                  >
                    {commandResults.map((r) => (
                      <li key={r.href + r.label} role="option">
                        <Link
                          href={r.href}
                          className="block px-3 py-2 text-sm text-foreground transition-colors hover:bg-surface-2"
                          onClick={() => {
                            setHeaderSearchOpen(false);
                            setHeaderSearch("");
                          }}
                        >
                          {r.label}
                        </Link>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </div>

              <div className="min-w-0 max-w-[min(100%,200px)] flex-1 sm:max-w-xs md:max-w-[min(100%,240px)] lg:max-w-xs">
                <p className="truncate text-sm font-bold tracking-tight text-foreground md:text-lg">
                  {title}
                </p>
                <p className="hidden text-xs text-muted-foreground sm:block md:hidden lg:block">
                  MasterSAT
                </p>
              </div>
            </div>

            <div className="flex shrink-0 flex-nowrap items-center gap-2 sm:gap-2.5 md:gap-3">
              <div className="hidden items-center gap-2 lg:flex">
                <span className="ds-section-title text-[9px]">Quick</span>
                {quickLinks.map((q) => (
                  <Link
                    key={q.href}
                    href={q.href}
                    className="inline-flex items-center gap-1 rounded-lg border border-border bg-card px-2.5 py-1.5 text-xs font-bold text-primary shadow-sm transition-all duration-200 hover:border-primary/35 hover:bg-primary/5"
                  >
                    <Zap className="h-3 w-3 opacity-80" />
                    {q.label}
                  </Link>
                ))}
              </div>

              <div className="relative" ref={notifRef}>
                <Tooltip content="Notifications" side="bottom">
                  <IconButton
                    variant="ghost"
                    aria-label="Notifications"
                    aria-expanded={notifOpen}
                    onClick={() => setNotifOpen((o) => !o)}
                    className="relative"
                  >
                    <Bell className="h-5 w-5" />
                    <span className="absolute right-1.5 top-1.5 h-1.5 w-1.5 rounded-full bg-primary opacity-60" aria-hidden />
                  </IconButton>
                </Tooltip>
                {notifOpen ? (
                  <div className="absolute right-0 top-[calc(100%+8px)] z-50 w-72 rounded-lg border border-border bg-card p-4 shadow-lg">
                    <p className="text-xs font-bold uppercase tracking-wider text-label-foreground">
                      Notifications
                    </p>
                    <p className="mt-3 text-sm text-muted-foreground">You&apos;re all caught up.</p>
                    <p className="mt-2 text-xs text-label-foreground">
                      Grades and assignments will appear here when available.
                    </p>
                  </div>
                ) : null}
              </div>

              {mounted && (
                <Tooltip
                  content={theme === "dark" ? "Light mode" : "Dark mode"}
                  side="bottom"
                  className="shrink-0"
                >
                  <IconButton
                    variant="default"
                    onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
                    aria-label="Toggle dark mode"
                    className="shrink-0"
                  >
                    {theme === "dark" ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
                  </IconButton>
                </Tooltip>
              )}

              {isLoggedIn ? (
                <Tooltip content="Profile" side="bottom" className="shrink-0">
                  <Link
                    href="/profile"
                    aria-label="Profile"
                    className={cn(
                      "relative inline-flex h-10 w-10 shrink-0 items-center justify-center overflow-hidden rounded-full border-2 border-primary/20 bg-card text-foreground shadow-sm transition-all hover:border-primary/40 hover:shadow-md",
                      "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50 focus-visible:ring-offset-2 focus-visible:ring-offset-background",
                    )}
                  >
                    {profileImageUrl && !profileAvatarFailed ? (
                      /* eslint-disable-next-line @next/next/no-img-element */
                      <img
                        src={profileImageUrl}
                        alt=""
                        className="absolute inset-0 h-full w-full object-cover"
                        onError={() => setProfileAvatarFailed(true)}
                      />
                    ) : (
                      <UserCircle className="h-5 w-5" strokeWidth={2} />
                    )}
                  </Link>
                </Tooltip>
              ) : (
                <button
                  type="button"
                  onClick={() => router.push("/login")}
                  className="inline-flex items-center gap-2 rounded-xl bg-primary px-3 py-2 text-xs font-bold text-primary-foreground hover:bg-primary/90 transition-colors md:px-4 md:text-sm"
                >
                  <LogIn className="h-4 w-4" />
                  <span className="hidden sm:inline">Sign in</span>
                </button>
              )}
            </div>
          </header>

          <main
            className={cn(
              "min-h-0 flex-1 overflow-y-auto overflow-x-hidden overscroll-y-contain bg-transparent px-2 pb-8 pt-2 md:px-4 md:pt-3 lg:px-6",
              globalInteractionBlockedHard && "pointer-events-none select-none",
            )}
            aria-busy={globalInteractionBlockedHard || undefined}
          >
            {children}
          </main>
        </div>
      </div>
    </AuthGuard>
  );
}
