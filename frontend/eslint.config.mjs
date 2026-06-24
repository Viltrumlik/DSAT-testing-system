import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
  ]),
  {
    rules: {
      // This codebase is mid-migration to stricter TS rules.
      // Keep lint actionable by not failing builds on `any` in app pages.
      "@typescript-eslint/no-explicit-any": "off",

      // Admin/editor pages intentionally touch DOM nodes (highlighting, previews, etc.).
      "react-hooks/immutability": "off",
      "react-hooks/purity": "off",
      "react-hooks/set-state-in-effect": "off",

      // Allow apostrophes in JSX text.
      "react/no-unescaped-entities": "off",
    },
  },
  // Staff consoles must never call public exam APIs (prevents route confusion regressions).
  {
    files: ["src/app/admin/**/*.{ts,tsx}", "src/app/(admin)/**/*.{ts,tsx}", "src/components/bulk-assign/**/*.{ts,tsx}"],
    rules: {
      "no-restricted-imports": [
        "error",
        {
          paths: [
            {
              name: "@/lib/api",
              importNames: ["examsPublicApi"],
              message: "Staff consoles must use examsAdminApi, not examsPublicApi.",
            },
          ],
        },
      ],
    },
  },
  // Bulk-assign must use its feature boundary (single choke point).
  {
    files: ["src/components/bulk-assign/**/*.{ts,tsx}"],
    rules: {
      "no-restricted-imports": [
        "error",
        {
          paths: [
            {
              name: "@/lib/api",
              importNames: ["examsAdminApi", "assessmentsAdminApi", "classesApi"],
              message: "Bulk-assign components must import APIs from '@/features/bulkAssign/api'.",
            },
          ],
        },
      ],
    },
  },
  // Teacher pages must use teacher feature boundary (reduces accidental surface drift).
  {
    files: ["src/app/(teacher)/**/*.{ts,tsx}"],
    rules: {
      "no-restricted-imports": [
        "error",
        {
          paths: [
            {
              name: "@/lib/api",
              importNames: ["examsAdminApi", "examsPublicApi", "classesApi"],
              message: "Teacher pages must import APIs from '@/features/teacher/api'.",
            },
          ],
        },
      ],
    },
  },
  // Student (main) pages and shared components must use feature boundaries for exams.
  {
    files: ["src/app/(main)/**/*.{ts,tsx}", "src/components/**/*.{ts,tsx}"],
    rules: {
      "no-restricted-imports": [
        "error",
        {
          paths: [
            {
              name: "@/lib/api",
              importNames: ["examsPublicApi", "examsAdminApi"],
              message:
                "Use feature APIs (e.g. '@/features/examsStudent/api') instead of importing exam clients from '@/lib/api'.",
            },
          ],
        },
      ],
    },
  },
  // Staff pages should prefer feature APIs over low-level clients.
  {
    files: ["src/app/admin/**/*.{ts,tsx}", "src/app/(admin)/**/*.{ts,tsx}"],
    rules: {
      "no-restricted-imports": [
        "error",
        {
          paths: [
            {
              name: "@/lib/api",
              importNames: ["examsAdminApi", "examsPublicApi", "assessmentsAdminApi"],
              message:
                "Admin pages must import exam/assessment clients via feature APIs (e.g. '@/features/adminExams/api', '@/features/adminAssessments/api'), not directly from '@/lib/api'.",
            },
          ],
        },
      ],
    },
  },
]);

export default eslintConfig;
