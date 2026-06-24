import { examsPublicApi } from "@/lib/api";

/**
 * Student exam surface (public catalog + attempt runner).
 * Pages/components must import from here, not from `@/lib/api`.
 */
export const examsStudentApi = examsPublicApi;

