"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle, Loader2, RefreshCw } from "lucide-react";
import { useMe } from "@/hooks/useMe";

const BOOT_TIMEOUT_MS = 12_000;
const BOOT_SLOW_MS = 5_000;

function consoleFromHostname(): "admin" | "questions" | "teacher" | "main" {
    if (typeof window === "undefined") return "main";
    const h = String(window.location.hostname || "").toLowerCase();
    const labels = h.split(".").filter(Boolean);
    if (!labels.length) return "main";
    if (labels[0] === "admin" || h.startsWith("admin.")) return "admin";
    if (labels[0] === "questions" || h.startsWith("questions.")) return "questions";
    if (labels.length >= 2 && labels[1] === "questions") return "questions";
    if (labels[0] === "teacher" || h.startsWith("teacher.")) return "teacher";
    return "main";
}

/** Absolute URL of the main student site, used to bounce unauthorized users off the teacher portal. */
const MAIN_SITE_URL =
    process.env.NEXT_PUBLIC_MAIN_SITE_URL || "https://mastersat.uz";

function permissionList(me: Record<string, unknown> | undefined | null): string[] {
    if (!me) return [];
    const p = me.permissions;
    if (!Array.isArray(p)) return [];
    return p.filter((x): x is string => typeof x === "string");
}

function staffAccess(perms: string[]): boolean {
    return (
        perms.includes("*") ||
        perms.includes("manage_users") ||
        perms.includes("assign_access") ||
        perms.includes("manage_tests")
    );
}

/**
 * `isOptional`: public shell (Marketing / browse) — never blocks on `/users/me`.
 * Strict guards: session required; `UNAUTHENTICATED` redirects to `/login` (`useMe` may set session notice → login page).
 *
 * Permission fields on `me` are **UX hints only** — backend remains authoritative on every mutation.
 */
export default function AuthGuard({
    children,
    isOptional = false,
    adminOnly = false,
}: {
    children: React.ReactNode;
    isOptional?: boolean;
    adminOnly?: boolean;
}) {
    const router = useRouter();
    const { bootState, me } = useMe();
    const bootTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const slowTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const [bootSlow, setBootSlow] = useState(false);
    const [bootTimedOut, setBootTimedOut] = useState(false);

    useEffect(() => {
        if (isOptional) return;
        if (bootState === "BOOTING") {
            slowTimerRef.current = setTimeout(() => setBootSlow(true), BOOT_SLOW_MS);
            bootTimerRef.current = setTimeout(() => setBootTimedOut(true), BOOT_TIMEOUT_MS);
        } else {
            setBootSlow(false);
            setBootTimedOut(false);
            if (bootTimerRef.current !== null) { clearTimeout(bootTimerRef.current); bootTimerRef.current = null; }
            if (slowTimerRef.current !== null) { clearTimeout(slowTimerRef.current); slowTimerRef.current = null; }
        }
        return () => {
            if (bootTimerRef.current !== null) { clearTimeout(bootTimerRef.current); bootTimerRef.current = null; }
            if (slowTimerRef.current !== null) { clearTimeout(slowTimerRef.current); slowTimerRef.current = null; }
        };
    }, [bootState, isOptional]);

    const consoleMode = consoleFromHostname();

    const roleRaw = String(me?.role ?? "").trim().toLowerCase();
    const perms = permissionList(me);
    const frozen = !!me?.is_frozen;
    const isTester = roleRaw === "test_admin";
    const isStudent = roleRaw === "student";
    const hasStaff = staffAccess(perms);
    // Teacher portal access is role-based (NOT permission-based): only teacher + super_admin.
    // This deliberately excludes admin/test_admin, unlike the perm-based admin console gate.
    const teacherPortalAllowed = roleRaw === "teacher" || roleRaw === "super_admin";

    useEffect(() => {
        if (bootState !== "AUTHENTICATED" || !me) return;
        // Teacher portal: only teacher + super_admin. Everyone else is bounced
        // cross-origin to the main site with the permission notice.
        if (consoleMode === "teacher" && !teacherPortalAllowed) {
            window.location.replace(`${MAIN_SITE_URL}/?denied=teacher-portal`);
            return;
        }
        if (frozen && !hasStaff) {
            router.replace("/frozen");
            return;
        }
        if (consoleMode === "questions" && isStudent) {
            router.replace("/");
            return;
        }
        if (consoleMode === "admin" && (isStudent || isTester)) {
            router.replace("/");
            return;
        }
        if (adminOnly && (!hasStaff || (consoleMode === "admin" && isTester))) {
            router.replace("/");
            return;
        }
    }, [
        bootState,
        me,
        frozen,
        hasStaff,
        isStudent,
        isTester,
        teacherPortalAllowed,
        adminOnly,
        consoleMode,
        router,
    ]);

    useEffect(() => {
        if (isOptional || bootState !== "UNAUTHENTICATED") return;
        router.replace("/login");
    }, [isOptional, bootState, router]);

    if (isOptional) {
        return <>{children}</>;
    }

    if (bootState === "BOOTING") {
        if (bootTimedOut) {
            return (
                <div className="min-h-screen bg-background flex flex-col items-center justify-center gap-4 px-6">
                    <AlertTriangle className="h-8 w-8 text-amber-500" />
                    <p className="text-sm font-semibold text-foreground text-center max-w-sm">
                        Taking too long to verify your session.
                    </p>
                    <p className="text-xs text-muted-foreground text-center max-w-sm">
                        This usually means the server is unreachable or your session has expired.
                    </p>
                    <div className="flex items-center gap-3">
                        <button
                            onClick={() => window.location.reload()}
                            className="inline-flex items-center gap-1.5 rounded-xl bg-primary px-4 py-2 text-sm font-bold text-primary-foreground hover:bg-primary/90 transition-colors"
                        >
                            <RefreshCw className="h-3.5 w-3.5" />
                            Retry
                        </button>
                        <Link href="/login" className="text-sm font-semibold text-primary underline">
                            Sign in
                        </Link>
                    </div>
                </div>
            );
        }
        return (
            <div className="min-h-screen bg-background flex flex-col items-center justify-center gap-3">
                <Loader2 className="h-10 w-10 animate-spin text-primary/60" aria-label="Loading" />
                {bootSlow && (
                    <p className="text-xs text-muted-foreground animate-in fade-in duration-300">
                        Verifying your session...
                    </p>
                )}
            </div>
        );
    }

    if (bootState === "UNAUTHENTICATED") {
        return (
            <div className="min-h-screen bg-background flex items-center justify-center">
                <Loader2 className="h-10 w-10 animate-spin text-primary/60" aria-label="Redirecting" />
            </div>
        );
    }

    if (!me) {
        return (
            <div className="min-h-screen bg-background flex flex-col items-center justify-center gap-4 px-6">
                <p className="text-sm text-muted-foreground text-center max-w-md">
                    Session could not be verified.
                </p>
                <Link href="/login" className="text-sm font-semibold text-primary underline">
                    Sign in
                </Link>
            </div>
        );
    }

    const willRedirectAway =
        (consoleMode === "teacher" && !teacherPortalAllowed) ||
        (frozen && !hasStaff) ||
        (consoleMode === "questions" && isStudent) ||
        (consoleMode === "admin" && (isStudent || isTester)) ||
        (adminOnly && (!hasStaff || (consoleMode === "admin" && isTester)));

    if (willRedirectAway) {
        return (
            <div className="min-h-screen bg-background flex items-center justify-center">
                <Loader2 className="h-8 w-8 animate-spin text-primary/60" aria-label="Redirecting" />
            </div>
        );
    }

    return <>{children}</>;
}
