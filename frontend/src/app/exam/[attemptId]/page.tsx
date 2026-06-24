"use client";
import { Suspense } from "react";
import AuthGuard from "@/components/AuthGuard";
import { ExamRunnerPage } from "@/features/testing-simulation";

/**
 * Route shell for the Testing Simulation. All exam logic lives in
 * `@/features/testing-simulation`; this file only wires auth + the Suspense
 * boundary required by `useSearchParams`.
 */
export default function ExamPlayerPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-screen items-center justify-center bg-white">
          <div className="h-10 w-10 animate-spin rounded-full border-4 border-blue-600 border-t-transparent" />
        </div>
      }
    >
      <AuthGuard>
        <ExamRunnerPage />
      </AuthGuard>
    </Suspense>
  );
}
