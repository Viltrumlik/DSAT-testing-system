"use client";

import { useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import Link from "next/link";
import { useTheme } from "next-themes";
import {
  Menu,
  X,
  Search,
  Bell,
  Sun,
  Moon,
  LogOut,
  LogIn,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import { cn } from "@/lib/cn";
import { Avatar } from "@/components/ui/Avatar";
import { IconButton } from "@/components/ui/IconButton";
import { Tooltip } from "@/components/ui/Tooltip";
import { Drawer } from "@/components/ui/Drawer";
import { EmptyState } from "@/components/ui/EmptyState";
import {
  flattenNav,
  isNavItemActive,
  pageTitleFor,
  type NavSection,
} from "./navConfig";

const COLLAPSE_KEY = "mastersat.sidebar.collapsed";

export type AppShellBrand = { name: string; tagline?: string; logoSrc?: string };
export type AppShellUser = { name?: string; avatarUrl?: string | null } | null;

export type AppShellProps = {
  brand: AppShellBrand;
  nav: NavSection[];
  pathname: string;
  user?: AppShellUser;
  profileHref?: string;
  onSignOut?: () => void;
  onSignIn?: () => void;
  children: React.ReactNode;
};

export function AppShell({
  brand,
  nav,
  pathname,
  user,
  profileHref = "/profile",
  onSignOut,
  onSignIn,
  children,
}: AppShellProps) {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [navQuery, setNavQuery] = useState("");
  const [cmd, setCmd] = useState("");
  const [cmdOpen, setCmdOpen] = useState(false);
  const [notifOpen, setNotifOpen] = useState(false);
  const cmdRef = useRef<HTMLDivElement>(null);

  useEffect(() => setMounted(true), []);
  useEffect(() => {
    try {
      setCollapsed(localStorage.getItem(COLLAPSE_KEY) === "1");
    } catch {
      /* ignore */
    }
  }, []);
  useEffect(() => setMobileOpen(false), [pathname]);
  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      const t = e.target as Node;
      if (cmdRef.current && !cmdRef.current.contains(t)) setCmdOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const toggleCollapsed = () =>
    setCollapsed((c) => {
      const n = !c;
      try {
        localStorage.setItem(COLLAPSE_KEY, n ? "1" : "0");
      } catch {
        /* ignore */
      }
      return n;
    });

  const filteredNav = useMemo(() => {
    const q = navQuery.trim().toLowerCase();
    if (!q) return nav;
    return nav
      .map((s) => ({ ...s, items: s.items.filter((i) => i.label.toLowerCase().includes(q)) }))
      .filter((s) => s.items.length > 0);
  }, [nav, navQuery]);

  const cmdResults = useMemo(() => {
    const flat = flattenNav(nav);
    const q = cmd.trim().toLowerCase();
    if (!q) return flat.slice(0, 6);
    return flat.filter((i) => i.label.toLowerCase().includes(q)).slice(0, 8);
  }, [nav, cmd]);

  // Material-style click ripple for nav items (matches the design reference).
  const addRipple = (e: ReactPointerEvent<HTMLElement>) => {
    const el = e.currentTarget;
    const rect = el.getBoundingClientRect();
    const size = Math.max(rect.width, rect.height);
    const span = document.createElement("span");
    span.className = "dz-ripple";
    span.style.cssText =
      `left:${e.clientX - rect.left}px;top:${e.clientY - rect.top}px;width:${size}px;height:${size}px`;
    el.appendChild(span);
    window.setTimeout(() => span.remove(), 600);
  };

  const title = pageTitleFor(nav, pathname, brand.name);
  const signedIn = !!user;

  return (
    <div className="ds-app flex min-h-screen flex-col bg-background text-foreground md:h-[100dvh] md:flex-row md:overflow-hidden">
      {mobileOpen ? (
        <button
          type="button"
          aria-label="Close menu"
          onClick={() => setMobileOpen(false)}
          className="fixed inset-0 z-[90] bg-[var(--overlay-scrim)] md:hidden"
        />
      ) : null}

      {/* Sidebar */}
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-[100] flex h-[100dvh] w-[min(100%,272px)] shrink-0 flex-col border-r border-border bg-card transition-[transform,width] duration-200 ease-[var(--ds-ease-premium)]",
          "md:relative md:z-30 md:h-full md:translate-x-0",
          collapsed ? "md:w-[4.5rem]" : "md:w-[272px]",
          mobileOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0",
        )}
      >
        {/* Brand */}
        <div
          className={cn(
            "flex h-16 items-center gap-3 border-b border-border px-4",
            collapsed && "md:justify-center md:px-0",
          )}
        >
          {brand.logoSrc ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={brand.logoSrc} alt={brand.name} className="h-12 w-12 shrink-0 object-contain" />
          ) : (
            <span className="flex h-9 w-9 shrink-0 items-center justify-center overflow-hidden rounded-xl bg-primary text-sm font-extrabold text-primary-foreground">
              {brand.name.slice(0, 1)}
            </span>
          )}
          {!collapsed ? (
            <div className="min-w-0 flex-1">
              <p className="truncate text-[19px] font-extrabold tracking-tight text-foreground">{brand.name}</p>
              {brand.tagline ? (
                <p className="ds-overline text-primary">{brand.tagline}</p>
              ) : null}
            </div>
          ) : null}
          <IconButton
            variant="ghost"
            size="sm"
            className="md:hidden"
            aria-label="Close navigation"
            onClick={() => setMobileOpen(false)}
          >
            <X className="h-4 w-4" />
          </IconButton>
        </div>

        {/* Filter */}
        {!collapsed ? (
          <div className="px-3 pt-3">
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-label-foreground" />
              <input
                value={navQuery}
                onChange={(e) => setNavQuery(e.target.value)}
                placeholder="Filter menu…"
                aria-label="Filter navigation"
                className="ds-ring h-9 w-full rounded-lg border border-border bg-surface-2 pl-9 pr-3 text-sm text-foreground placeholder:text-label-foreground focus-visible:border-primary"
              />
            </div>
          </div>
        ) : null}

        {/* Nav */}
        <nav
          aria-label="Main"
          className={cn(
            "flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-3 py-4",
            collapsed && "md:items-center md:px-2",
          )}
        >
          {filteredNav.length === 0 ? (
            <p className="px-2 py-6 text-center text-sm text-muted-foreground">
              No sections match.
            </p>
          ) : (
            filteredNav.map(({ section, items }, sIdx) => (
              <div
                key={section}
                className="flex flex-col gap-[7px]"
                style={{ animation: "dz-sectionIn .42s cubic-bezier(.22,1,.36,1) both", animationDelay: `${sIdx * 60}ms` }}
              >
                {!collapsed && section ? (
                  <p className="px-3.5 pb-2 pt-[18px] text-[11px] font-extrabold uppercase tracking-[0.14em] text-label-foreground">
                    {section}
                  </p>
                ) : null}
                {items.map(({ href, label, icon: Icon, isNew }) => {
                  const active = isNavItemActive(href, pathname);
                  const link = (
                    <Link
                      key={href}
                      href={href}
                      onClick={() => setMobileOpen(false)}
                      onPointerDown={addRipple}
                      aria-current={active ? "page" : undefined}
                      className={cn(
                        "ds-ring group relative flex items-center gap-[13px] overflow-hidden rounded-[13px] border-[1.5px] px-3.5 py-[11px] text-[15px] font-semibold transition-[background-color,color,transform,border-color,box-shadow] duration-200 active:scale-[0.96]",
                        collapsed && "md:justify-center md:px-2",
                        active
                          ? "border-primary bg-primary-soft font-bold text-primary hover:translate-x-0.5 hover:shadow-[0_6px_16px_rgba(42,104,192,0.18)]"
                          : "border-border bg-transparent text-muted-foreground hover:translate-x-[3px] hover:border-primary hover:text-primary",
                      )}
                    >
                      <Icon
                        className={cn("h-5 w-5 shrink-0", active && "[animation:dz-navPop_0.4s_ease]")}
                        strokeWidth={2}
                      />
                      {!collapsed ? <span className="flex-1 truncate">{label}</span> : null}
                      {!collapsed && isNew ? (
                        <span className="rounded-md bg-success-soft px-1.5 py-0.5 text-[10px] font-extrabold uppercase tracking-[0.08em] text-success-foreground">
                          New
                        </span>
                      ) : null}
                    </Link>
                  );
                  return collapsed ? (
                    <Tooltip key={href} content={label} side="right">
                      {link}
                    </Tooltip>
                  ) : (
                    link
                  );
                })}
              </div>
            ))
          )}
        </nav>

        {/* Footer */}
        <div className={cn("mt-auto border-t border-border p-3", collapsed && "md:px-2")}>
          {signedIn && onSignOut ? (
            <button
              type="button"
              onClick={onSignOut}
              className={cn(
                "ds-ring flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-semibold text-muted-foreground transition-colors hover:bg-surface-2 hover:text-foreground",
                collapsed && "md:justify-center md:px-2",
              )}
            >
              <LogOut className="h-[18px] w-[18px] shrink-0" />
              {!collapsed ? "Sign out" : null}
            </button>
          ) : null}
          <IconButton
            variant="ghost"
            size="sm"
            className="mt-1 hidden w-full md:flex"
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            onClick={toggleCollapsed}
          >
            {collapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
          </IconButton>
        </div>
      </aside>

      {/* Main column */}
      <div className="relative flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
        {/* Large faint brand watermark — sits behind all page content */}
        {brand.logoSrc ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={brand.logoSrc}
            alt=""
            aria-hidden
            className="pointer-events-none absolute -bottom-20 -right-16 z-0 w-[min(55vw,560px)] select-none opacity-[0.045] dark:opacity-[0.07]"
          />
        ) : null}
        <header className="sticky top-0 z-40 flex h-16 shrink-0 items-center gap-2 border-b border-border bg-card/80 px-3 backdrop-blur md:gap-4 md:px-6">
          <IconButton
            variant="ghost"
            className="md:hidden"
            aria-label="Open menu"
            onClick={() => setMobileOpen(true)}
          >
            <Menu className="h-5 w-5" />
          </IconButton>

          <div ref={cmdRef} className="relative hidden min-w-0 max-w-md flex-1 md:block">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-label-foreground" />
            <input
              value={cmd}
              onChange={(e) => {
                setCmd(e.target.value);
                setCmdOpen(true);
              }}
              onFocus={() => setCmdOpen(true)}
              placeholder="Search pages…"
              aria-label="Search pages"
              className="ds-ring h-10 w-full rounded-xl border border-border bg-surface-2 pl-9 pr-3 text-sm text-foreground placeholder:text-label-foreground focus-visible:border-primary"
            />
            {cmdOpen && cmdResults.length > 0 ? (
              <ul className="ds-anim-fade absolute left-0 right-0 top-[calc(100%+6px)] z-50 max-h-72 overflow-auto rounded-xl border border-border bg-card py-1 shadow-modal">
                {cmdResults.map((r) => (
                  <li key={r.href}>
                    <Link
                      href={r.href}
                      onClick={() => {
                        setCmdOpen(false);
                        setCmd("");
                      }}
                      className="flex items-center gap-2.5 px-3 py-2 text-sm text-foreground transition-colors hover:bg-surface-2"
                    >
                      <r.icon className="h-4 w-4 text-label-foreground" />
                      {r.label}
                    </Link>
                  </li>
                ))}
              </ul>
            ) : null}
          </div>

          <p className="truncate text-base font-bold tracking-tight md:hidden">{title}</p>

          <div className="ml-auto flex shrink-0 items-center gap-1.5 md:gap-2">
            <Tooltip content="Notifications" side="bottom">
              <IconButton
                variant="ghost"
                aria-label="Notifications"
                aria-expanded={notifOpen}
                onClick={() => setNotifOpen(true)}
                className="relative"
              >
                <Bell className="h-5 w-5" />
                <span className="absolute right-1.5 top-1.5 h-1.5 w-1.5 rounded-full bg-primary" aria-hidden />
              </IconButton>
            </Tooltip>

            {mounted ? (
              <Tooltip content={theme === "dark" ? "Light mode" : "Dark mode"} side="bottom">
                <IconButton
                  variant="default"
                  aria-label="Toggle theme"
                  onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
                >
                  {theme === "dark" ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
                </IconButton>
              </Tooltip>
            ) : null}

            {signedIn ? (
              <Link href={profileHref} aria-label="Profile" className="ds-ring rounded-full">
                <Avatar src={user?.avatarUrl} name={user?.name} size={38} />
              </Link>
            ) : onSignIn ? (
              <button
                type="button"
                onClick={onSignIn}
                className="ds-ring inline-flex items-center gap-2 rounded-xl bg-primary px-3 py-2 text-sm font-bold text-primary-foreground transition-colors hover:bg-primary-hover md:px-4"
              >
                <LogIn className="h-4 w-4" />
                <span className="hidden sm:inline">Sign in</span>
              </button>
            ) : null}
          </div>
        </header>

        <main className="relative z-10 min-h-0 flex-1 overflow-y-auto px-3 py-5 md:px-6 lg:px-8">{children}</main>
      </div>

      {/* Notifications — bell opens a drawer (not a primary nav item) */}
      <Drawer
        open={notifOpen}
        onClose={() => setNotifOpen(false)}
        title="Notifications"
      >
        <EmptyState
          compact
          icon={Bell}
          title="You're all caught up"
          description="Grades, assignments, and reminders will appear here."
        />
      </Drawer>
    </div>
  );
}
