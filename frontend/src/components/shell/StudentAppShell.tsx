"use client";

import { usePathname } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import AuthGuard from "@/components/AuthGuard";
import { authApi } from "@/lib/api";
import { useMe } from "@/hooks/useMe";
import { cn } from "@/lib/cn";
import { AppShell } from "./AppShell";
import { studentNav } from "./navConfig";

/** Wires the generic AppShell with student auth, identity, and IA. */
export default function StudentAppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const queryClient = useQueryClient();
  const { isAuthenticated, me, globalInteractionBlockedHard } = useMe();

  const m = me as { first_name?: string; last_name?: string; profile_image_url?: string | null } | undefined;
  const name = [m?.first_name, m?.last_name].filter(Boolean).join(" ").trim() || undefined;

  return (
    <AuthGuard>
      <AppShell
        brand={{ name: "MasterSAT", logoSrc: "/images/logo.png" }}
        nav={studentNav}
        pathname={pathname}
        user={isAuthenticated ? { name, avatarUrl: m?.profile_image_url ?? null } : null}
        onSignOut={() => authApi.logout(queryClient)}
      >
        <div className={cn(globalInteractionBlockedHard && "pointer-events-none select-none")} aria-busy={globalInteractionBlockedHard || undefined}>
          {children}
        </div>
      </AppShell>
    </AuthGuard>
  );
}
