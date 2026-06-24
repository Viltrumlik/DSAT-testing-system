import { NextResponse } from "next/server";

// Standalone exam-runner is single-host. The monorepo middleware did per-subdomain
// console routing (admin/questions/teacher); none of that applies here. Route
// protection lives in <AuthGuard> / <AuthGuard adminOnly> at the layout level.
export function middleware() {
  return NextResponse.next();
}

export const config = { matcher: [] };
