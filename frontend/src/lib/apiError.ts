import type { AxiosError } from "axios";

export type ApiError = {
  status: number;
  message: string;
  code?: string;
  fieldErrors?: Record<string, string[]>;
};

function asRecord(x: unknown): Record<string, unknown> | null {
  if (!x || typeof x !== "object") return null;
  return x as Record<string, unknown>;
}

export function normalizeApiError(err: unknown): ApiError {
  const fallback: ApiError = { status: 0, message: "Request failed." };

  const ax = err as AxiosError | undefined;
  const status = (ax as any)?.response?.status;
  const data = (ax as any)?.response?.data;

  if (typeof status === "number") {
    const rec = asRecord(data);
    const detail =
      typeof rec?.detail === "string"
        ? rec.detail
        : typeof (data as any) === "string"
          ? String(data)
          : null;

    const fieldErrors: Record<string, string[]> = {};
    if (rec) {
      for (const [k, v] of Object.entries(rec)) {
        if (k === "detail") continue;
        if (Array.isArray(v) && v.every((x) => typeof x === "string")) {
          fieldErrors[k] = v as string[];
        }
      }
    }

    return {
      status,
      message: detail || (status === 403 ? "Forbidden." : status === 401 ? "Unauthorized." : "Request failed."),
      ...(typeof rec?.code === "string" ? { code: rec.code } : {}),
      ...(Object.keys(fieldErrors).length ? { fieldErrors } : {}),
    };
  }

  if (err instanceof Error && err.message) {
    return { ...fallback, message: err.message };
  }

  return fallback;
}

