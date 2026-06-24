import axios, { type AxiosError, type AxiosResponse } from 'axios';
import type { TelegramOIDCResult } from "@/types/telegramAuth";
import { buildSanitizedAuthCorrelationHeaders } from "@/lib/auth/authCorrelation";
import { evaluateAuthCircuitBreaker, noteTemporalStaleRejection } from "@/lib/auth/authCircuitBreaker";
import {
    getAuthLossVersion,
    markAuthLossDetected,
    shouldBlockMutatingRequests,
    tryScheduleAuthRedirect,
} from "@/lib/auth/authConcurrency";
import { pushGlobalToastOnce } from "@/lib/toastBus";
import type { QueryClient } from "@tanstack/react-query";
import Cookies from 'js-cookie';
import {
    AUTH_NOTICE_STORAGE_KEY,
    broadcastLogoutToOtherTabs,
} from "@/lib/auth/authTabSync";
import { meQueryKey } from "@/lib/auth/meQueryKey";
import type { TestAttempt } from "@/features/examsStudent/testAttemptSchema";
import {
    parseMockExamPublicList,
    parseMockExamPublicPayload,
    parsePracticeTestPublicList,
    parsePracticeTestPublicPayload,
    parseTestAttemptApiPayload,
    parseTestAttemptList,
    type MockExamPublic,
    type NormalizedExamList,
    type PracticeTestPublic,
} from "@/lib/examsPublicContract";
import {
    parseAssignmentList,
    parseAuthSessionPayload,
    parseBulkAssignResponse,
    parseBulkAssignmentHistoryList,
    parseClassroomList,
    parseCsrfPayload,
    parseUserMePayload,
    type Assignment,
    type BulkAssignmentDispatch,
    type Classroom,
    type NormalizedList,
    type UserMe,
} from "@/lib/criticalApiContract";

export type { MockExamPublic, NormalizedExamList, PracticeTestPublic } from "@/lib/examsPublicContract";
export { InvalidApiPayloadError, emptyNormalizedExamList } from "@/lib/examsPublicContract";
export type { Assignment, BulkAssignmentDispatch, Classroom, NormalizedList, UserMe } from "@/lib/criticalApiContract";

// ── Pastpaper section types ──────────────────────────────────────────────────
/**
 * A single standalone pastpaper SECTION (one `PracticeTest`, subject MATH or
 * READING_WRITING). The former `PastpaperPack` grouping was removed on the
 * backend; sections now carry `collection_name` (the former pack title) for
 * grouping/labeling. Returned by GET /exams/ (student) and
 * GET /exams/admin/tests/ (admin).
 */
export type PastpaperModuleBrief = {
    id: number;
    module_order?: number | null;
    time_limit_minutes?: number | null;
};

export type PastpaperSection = {
    id: number;
    title: string;
    practice_date: string | null;
    subject: string; // "MATH" | "READING_WRITING"
    label: string;
    form_type: string; // "INTERNATIONAL" | "US"
    collection_name: string;
    is_published: boolean;
    modules: PastpaperModuleBrief[];
    created_at?: string;
    mock_exam_id?: number | null;
};

/** Admin section row (GET /exams/admin/tests/). Extends the student shape with admin fields. */
export type AdminPastpaperSection = PastpaperSection & {
    published_at?: string | null;
    mock_exam?: number | null;
    assigned_users?: number[];
};

/** Violation entry returned when publishing a section is blocked by SAT rules. */
export type SectionPublishViolation = { code: string; message: string };

export { emptyNormalizedList } from "@/lib/criticalApiContract";

/** Tighter budget for bootstrap identity probes (UX: fail faster to login/error path). */
export const ME_REQUEST_TIMEOUT_MS = 10_000;
/**
 * Axios default timeout for all other requests (CSRF/refresh/etc.).
 * Required so a wedged `/auth/refresh/` cannot leave `/users/me` hanging forever behind the 401 interceptor.
 */
export const HTTP_CLIENT_TIMEOUT_MS = 35_000;

const API_URL = '/api';
const IS_PROD = process.env.NODE_ENV === 'production';

function cookieDomain(): string | undefined {
    if (typeof window === "undefined") return undefined;
    const host = window.location.hostname.toLowerCase();
    // Share auth cookies across subdomains in production.
    if (host.endsWith("mastersat.uz")) return ".mastersat.uz";
    return undefined;
}

const AUTH_COOKIE_NAMES = [
    // Legacy JS-readable tokens (removed); still cleared defensively.
    "access_token",
    "refresh_token",
    "is_admin",
    "is_frozen",
    "role",
    "lms_permissions",
    "lms_scope",
    "lms_user",
] as const;

/** Remove JS-readable auth **projection** cookies only (not HttpOnly session cookies). */
export function clearDerivedAuthProjectionCookies() {
    if (typeof window === "undefined") return;
    const host = window.location.hostname;
    const sharedDomain = cookieDomain();
    const domains = [undefined, host, sharedDomain].filter(Boolean) as (string | undefined)[];
    const paths = ["/"];
    const names = ["lms_user", "lms_permissions"] as const;
    for (const name of names) {
        for (const path of paths) {
            Cookies.remove(name, { path });
            for (const domain of domains) {
                Cookies.remove(name, { path, domain });
            }
        }
    }
}

export function clearAuthCookiesEverywhere() {
    if (typeof window === "undefined") return;
    const host = window.location.hostname;
    const sharedDomain = cookieDomain();
    const domains = [undefined, host, sharedDomain].filter(Boolean) as (string | undefined)[];
    const paths = ["/"];

    for (const name of AUTH_COOKIE_NAMES) {
        for (const path of paths) {
            Cookies.remove(name, { path });
            for (const domain of domains) {
                Cookies.remove(name, { path, domain });
            }
        }
    }
}

/** JS-readable projection of GET /users/me/ — not used for authorization decisions */
export function writeLmsUserCacheFromMe(me: unknown, rememberMe: boolean): void {
    if (typeof window === "undefined" || !me || typeof me !== "object") return;
    const m = me as Record<string, unknown>;
    const cookieOptions = {
        secure: IS_PROD,
        sameSite: "lax" as const,
        expires: rememberMe ? 7 : undefined,
        domain: IS_PROD ? cookieDomain() : undefined,
        path: "/" as const,
    };
    const rawPerms = m.permissions;
    const permissions = Array.isArray(rawPerms) ? rawPerms.filter((x) => typeof x === "string") : [];
    Cookies.set(
        "lms_user",
        JSON.stringify({
            id: m.id,
            email: m.email,
            username: m.username,
            first_name: m.first_name,
            last_name: m.last_name,
            role: m.role ? String(m.role).toLowerCase() : "",
            subject: m.subject ? String(m.subject).toLowerCase() : "",
            permissions,
            is_frozen: !!m.is_frozen,
            is_admin: !!m.is_admin,
        }),
        cookieOptions,
    );
    Cookies.remove("lms_subject", { path: "/", domain: IS_PROD ? cookieDomain() : undefined });
}

async function persistMeCookie(rememberMe: boolean) {
    try {
        const r = await api.get("/users/me/", {
            timeout: ME_REQUEST_TIMEOUT_MS,
        });
        const me = parseUserMePayload(r.data, "GET /users/me/ (persist cookie)");
        writeLmsUserCacheFromMe(me, rememberMe);
    } catch {
        clearDerivedAuthProjectionCookies();
    }
}

const api = axios.create({
    baseURL: API_URL,
    timeout: HTTP_CLIENT_TIMEOUT_MS,
    withCredentials: true,
});

/** POST with retries on 429 (and transient 503): exponential backoff, honors Retry-After when present. */
async function axiosPostWith429Backoff<T>(
    call: () => Promise<AxiosResponse<T>>,
    options?: { maxRetries?: number; baseDelayMs?: number; maxDelayMs?: number },
): Promise<AxiosResponse<T>> {
    const maxRetries = options?.maxRetries ?? 5;
    const baseDelayMs = options?.baseDelayMs ?? 800;
    const maxDelayMs = options?.maxDelayMs ?? 30_000;
    let lastError: unknown;
    for (let attempt = 0; attempt <= maxRetries; attempt++) {
        try {
            return await call();
        } catch (err: unknown) {
            lastError = err;
            const ax = err as AxiosError;
            const status = ax.response?.status;
            const retryable = status === 429 || status === 503;
            if (retryable && attempt < maxRetries) {
                const ra = ax.response?.headers?.['retry-after'];
                const raSec = ra != null ? parseInt(String(ra), 10) : NaN;
                const fromHeader = Number.isFinite(raSec) && raSec > 0 ? raSec * 1000 : null;
                const backoff = fromHeader ?? Math.min(maxDelayMs, baseDelayMs * 2 ** attempt);
                await new Promise((r) => setTimeout(r, backoff));
                continue;
            }
            break;
        }
    }
    throw lastError;
}

/** DRF may return a bare array or a paginated ``{ results: [...] }`` object. */
function unwrapAdminList<T>(data: unknown): T[] {
    if (Array.isArray(data)) return data as T[];
    if (data && typeof data === 'object' && Array.isArray((data as { results?: unknown }).results)) {
        return (data as { results: T[] }).results;
    }
    return [];
}

/** Admin exam list payloads always include a numeric primary key. */
type AdminListEntity = { id: number };

function urlSkipsTemporalStaleCheck(relUrl: string): boolean {
    const u = String(relUrl || "").toLowerCase();
    return (
        u.includes("/auth/refresh") ||
        u.includes("/auth/login") ||
        u.includes("/auth/logout") ||
        u.includes("/auth/csrf") ||
        u.includes("/auth/client-telemetry")
    );
}

// CSRF token source of truth for the X-CSRFToken header.
//
// We deliberately do NOT read `Cookies.get("csrftoken")` from document.cookie:
// if the browser has multiple csrftoken cookies (e.g. a legacy per-subdomain copy
// from a past DEBUG=True period alongside the current Domain=.mastersat.uz copy),
// js-cookie returns the FIRST and Django reads the LAST, producing a permanent
// CSRF mismatch ("CSRF token from the 'X-CSRFToken' HTTP header incorrect.").
//
// Instead we cache the masked token from GET /auth/csrf/ JSON body. Django's CSRF
// middleware unmasks it on each request and compares against the cookie SECRET it
// happens to read — both sides converge on the same cookie value, eliminating the
// JS-vs-Django parser-order disagreement.
let _maskedCsrfToken: string | null = null;
let _maskedCsrfFetch: Promise<string> | null = null;

async function getMaskedCsrfToken(): Promise<string> {
    if (_maskedCsrfToken) return _maskedCsrfToken;
    if (_maskedCsrfFetch) return _maskedCsrfFetch;
    _maskedCsrfFetch = (async () => {
        try {
            const r = await api.get("/auth/csrf/");
            const payload = parseCsrfPayload(r.data, "GET /auth/csrf/");
            const tok = String((payload as any)?.csrfToken || "");
            _maskedCsrfToken = tok || null;
            return _maskedCsrfToken || "";
        } finally {
            _maskedCsrfFetch = null;
        }
    })();
    return _maskedCsrfFetch;
}

/** Invalidate the cached CSRF token; the next mutation re-fetches a fresh one. */
function invalidateMaskedCsrfToken(): void {
    _maskedCsrfToken = null;
}

api.interceptors.request.use(async (config) => {
    // Auth is cookie-based (HttpOnly access token). Do not attach Authorization header.
    // CSRF hardening: send X-CSRFToken for unsafe methods using the cached MASKED token
    // (sourced from /auth/csrf/ JSON body, NOT from document.cookie — see above).
    try {
        (config as unknown as Record<string, unknown>).__mastersatEnqueueLossVer = getAuthLossVersion();
        const method = String(config.method || "get").toLowerCase();
        if (shouldBlockMutatingRequests(method, String(config.url || ""))) {
            return Promise.reject(
                Object.assign(new Error("AUTH_CONCURRENCY_BLOCKED"), { __mastersatConcurrencyBlocked: true }),
            );
        }
        const hdrs = buildSanitizedAuthCorrelationHeaders();
        (config.headers as any) = config.headers || {};
        Object.assign(config.headers as Record<string, string>, hdrs);

        const unsafe = method !== "get" && method !== "head" && method !== "options";
        if (unsafe) {
            const url = String(config.url || "");
            // Never await the CSRF fetch for the CSRF endpoint itself (chicken-and-egg).
            // Also skip for the very first auth endpoints where the cookie may not exist yet —
            // Django marks them CSRF-exempt anyway, but we still emit the header if we have it.
            const isAuthBootstrap =
                url.includes("/auth/csrf/") ||
                url.includes("/auth/login/") ||
                url.includes("/auth/refresh/");
            try {
                const tok = isAuthBootstrap
                    ? (_maskedCsrfToken || Cookies.get("csrftoken") || "")
                    : await getMaskedCsrfToken();
                if (tok) {
                    (config.headers as any)["X-CSRFToken"] = tok;
                }
            } catch {
                // Fall back to cookie value to avoid blocking the request entirely.
                const fallback = Cookies.get("csrftoken");
                if (fallback) (config.headers as any)["X-CSRFToken"] = fallback;
            }
        }
    } catch {
        // ignore
    }
    return config;
});

api.interceptors.response.use(
    (response: AxiosResponse) => {
        try {
            const cfg = response.config as unknown as Record<string, unknown> | undefined;
            const url = String(cfg?.url ?? "");
            if (!urlSkipsTemporalStaleCheck(url) && typeof cfg?.__mastersatEnqueueLossVer === "number") {
                const enq = cfg.__mastersatEnqueueLossVer as number;
                if (getAuthLossVersion() > enq) {
                    return Promise.reject(
                        Object.assign(new Error("AUTH_TEMPORAL_STALE"), {
                            __mastersatTemporalStale: true,
                            __mastersatStaleResponse: response,
                        }),
                    );
                }
            }
        } catch {
            /* ignore */
        }
        return response;
    },
    async (error) => {
        const ex = error as { message?: string; __mastersatTemporalStale?: boolean };
        if (ex?.message === "AUTH_TEMPORAL_STALE" || ex?.__mastersatTemporalStale) {
            noteTemporalStaleRejection();
            pushGlobalToastOnce(
                "auth.temporal-stale.retry",
                {
                    tone: "neutral",
                    message:
                        "Your session advanced while we were completing that step. Anything already saved stayed saved — please try once more.",
                },
                16_000,
            );
            if (evaluateAuthCircuitBreaker()) {
                window.dispatchEvent(new Event("mastersat-auth-circuit-trip"));
            }
            return Promise.reject(error);
        }

        if (error.response?.status === 403 && error.response?.data?.detail) {
            if (typeof window !== 'undefined') {
                // Avoid blocking alerts (and leaking backend detail strings) in production UX.
                console.warn("Forbidden:", error.response.data.detail);
            }
            // CSRF mismatch self-heal: if Django rejected the token (common after stale
            // legacy cookies are cleared, or after the masked-token cache went out of sync),
            // drop the cached token, fetch a fresh one, and retry the original request once.
            const original = error.config as any;
            const detail = String(error.response.data.detail || "").toLowerCase();
            const looksLikeCsrf =
                detail.includes("csrf") ||
                detail === "csrf failed." ||
                detail.includes("origin");
            if (looksLikeCsrf && original && !original.__csrfRetryAttempted) {
                original.__csrfRetryAttempted = true;
                try {
                    invalidateMaskedCsrfToken();
                    await getMaskedCsrfToken();
                    return api(original);
                } catch {
                    // fall through to normal 403 rejection
                }
            }
        }

        // Auth hardening for long-running sessions (exams):
        // On 401, attempt a token refresh once, then retry the original request.
        // Only redirect to /login if refresh fails.
        if (error.response?.status === 401) {
            if (typeof window !== "undefined" && (globalThis as any).__mastersatLogoutInProgress) {
                return Promise.reject(error);
            }
            const original = error.config as any;
            const originalUrl = String(original?.url ?? "");
            // Never try to refresh when the failing request IS an auth endpoint — doing so
            // creates a circular promise deadlock: the refresh 401 re-enters the interceptor,
            // awaits __mastersatRefreshPromise, which is itself awaiting the refresh POST,
            // which is waiting for the interceptor → infinite hang.
            const isAuthEndpoint =
                originalUrl.includes("/auth/refresh/") ||
                originalUrl.includes("/auth/csrf/") ||
                originalUrl.includes("/auth/login/");
            // Known-public endpoints. A stale JWT must NEVER trigger a refresh/redirect cycle on these
            // — they are reachable while logged-out and the page (especially /login itself) polls them
            // on every render. A 401 here historically caused: refresh → fail → redirect to /login →
            // re-render → poll public endpoint → 401 → ... (visible as "page constantly reloading").
            const isPublicEndpoint =
                originalUrl.includes("/users/telegram/config/") ||
                originalUrl.includes("/users/telegram/start/") ||
                originalUrl.includes("/users/telegram/callback/") ||
                originalUrl.includes("/users/register/") ||
                originalUrl.includes("/users/google/") ||
                originalUrl.includes("/users/telegram/") ||
                originalUrl.includes("/health/");
            if (isPublicEndpoint) {
                return Promise.reject(error);
            }

            if (original && !original.__isRetryRequest && !isAuthEndpoint) {
                original.__isRetryRequest = true;
                try {
                    // Shared refresh promise to avoid thundering herd.
                    // Refresh uses HttpOnly cookie `lms_refresh`; no JS-readable tokens.
                    if (!(globalThis as any).__mastersatRefreshPromise) {
                        (globalThis as any).__mastersatRefreshPromise = (async () => {
                            // Use the shared axios instance so CSRF headers apply.
                            await authApi.csrf();
                            await api.post("/auth/refresh/", {});
                            return true;
                        })().finally(() => {
                            (globalThis as any).__mastersatRefreshPromise = null;
                        });
                    }
                    await (globalThis as any).__mastersatRefreshPromise;
                    return api(original);
                } catch {
                    // fall through to logout/redirect
                }
            }

            if (typeof window !== "undefined") {
                const url = originalUrl;
                // `/users/me` is bootstrap-only; app layer (`useMe`, `AuthGuard`) decides redirect/session UX.
                if (url.includes("users/me")) {
                    return Promise.reject(error);
                }
                const path = String(window.location?.pathname || "");
                const inExamRunner = path.startsWith("/exam/");
                if (inExamRunner) {
                    const e: any = error;
                    e.__mastersatAuthRequired = true;
                    return Promise.reject(e);
                }
                // If we're already on a public auth page, do NOT redirect — that would reload the
                // current page in a tight loop the moment the user has any stale JWT cookie. Just
                // clear the bad cookies and let the page render normally.
                const onAuthPage = path === "/login" || path === "/register" || path.startsWith("/login/") || path.startsWith("/register/");
                if (onAuthPage) {
                    clearAuthCookiesEverywhere();
                    return Promise.reject(error);
                }
                (globalThis as any).__mastersatLogoutInProgress = true;
            }
            clearAuthCookiesEverywhere();
            if (typeof window !== "undefined") {
                markAuthLossDetected("EXPIRED");
                tryScheduleAuthRedirect(() => {
                    window.location.href = "/login";
                });
            }
        }
        return Promise.reject(error);
    }
);

export const usersApi = {
    getMe: async (opts?: { signal?: AbortSignal }): Promise<UserMe> => {
        const signal = opts?.signal;
        const r = await api.get("/users/me/", {
            signal,
            timeout: ME_REQUEST_TIMEOUT_MS,
        });
        if (signal?.aborted) {
            throw new DOMException("Aborted", "AbortError");
        }
        return parseUserMePayload(r.data, "GET /users/me/");
    },
    patchMe: async (data: FormData | Record<string, unknown>): Promise<UserMe> => {
        const r = await api.patch('/users/me/', data);
        return parseUserMePayload(r.data, "PATCH /users/me/");
    },
    /** Public: Telegram OIDC config. ``start_url`` is the server-mediated OAuth entry point. */
    getTelegramWidgetConfig: async (): Promise<{
        enabled: boolean;
        bot_username: string | null;
        client_id: string | null;
        start_url: string | null;
    }> => {
        const r = await api.get('/users/telegram/config/');
        return r.data;
    },
    /** Link Telegram to the logged-in user (profile). Pass the ``id_token`` from Telegram.Login.auth. */
    linkTelegram: async (idToken: string): Promise<UserMe> => {
        const r = await api.post('/users/telegram/link/', { id_token: idToken });
        return parseUserMePayload(r.data, "POST /users/telegram/link/");
    },
    /** Active SAT/exam dates for profile dropdown (admin-managed). */
    listExamDates: async () => {
        const r = await api.get('/users/exam-dates/');
        return r.data;
    },
};

export const authApi = {
    csrf: async () => {
        // Must be called before login/refresh/logout on hardened CSRF flows.
        // Also refreshes the in-memory masked-token cache used by the request interceptor.
        const r = await api.get("/auth/csrf/");
        const payload = parseCsrfPayload(r.data, "GET /auth/csrf/");
        try {
            const tok = String((payload as any)?.csrfToken || "");
            if (tok) {
                _maskedCsrfToken = tok;
            }
        } catch {
            /* ignore */
        }
        return payload;
    },
    register: async (firstName: string, lastName: string, username: string, email: string, password: string) => {
        const response = await api.post('/users/register/', { 
            first_name: firstName,
            last_name: lastName,
            username: username,
            email, 
            password
        });
        return parseAuthSessionPayload(response.data, "POST /users/register/");
    },
    login: async (email: string, password: string, rememberMe = true) => {
        // Avoid "sticky sessions" when old host-only + shared-domain cookies both exist.
        clearAuthCookiesEverywhere();
        await authApi.csrf();
        const response = await api.post('/auth/login/', { email, password, remember_me: rememberMe ? 1 : 0 });
        await persistMeCookie(rememberMe);
        return parseAuthSessionPayload(response.data, "POST /auth/login/");
    },
    googleAuth: async (credential: string, profile?: { first_name?: string; last_name?: string; username?: string }, rememberMe = true) => {
        clearAuthCookiesEverywhere();
        await authApi.csrf();
        const response = await api.post('/users/google/', { credential, ...(profile || {}) });
        await persistMeCookie(rememberMe);
        return parseAuthSessionPayload(response.data, "POST /users/google/");
    },
    telegramAuth: async (idToken: string, rememberMe = true) => {
        clearAuthCookiesEverywhere();
        await authApi.csrf();
        const response = await api.post('/users/telegram/', { id_token: idToken });
        await persistMeCookie(rememberMe);
        return parseAuthSessionPayload(response.data, "POST /users/telegram/");
    },
    logout: async (queryClient?: QueryClient | null) => {
        try {
            await authApi.csrf();
            await api.post("/auth/logout/", {});
        } catch {
            // ignore
        }
        try {
            localStorage.removeItem(AUTH_NOTICE_STORAGE_KEY);
        } catch {
            /* ignore */
        }
        broadcastLogoutToOtherTabs();
        clearAuthCookiesEverywhere();
        queryClient?.removeQueries({ queryKey: [...meQueryKey] });
        window.location.href = '/login';
    },
    refresh: async (_rememberMe = true) => {
        await authApi.csrf();
        const response = await api.post("/auth/refresh/", {});
        return parseAuthSessionPayload(response.data, "POST /auth/refresh/");
    },
    getSessions: async () => {
        const r = await api.get("/auth/sessions/");
        return r.data as { sessions: any[] };
    },
    revokeSession: async (sessionId: number) => {
        const r = await api.post(`/auth/sessions/${sessionId}/revoke/`, {});
        return r.data;
    },
    revokeAllSessions: async () => {
        const r = await api.post("/auth/sessions/revoke_all/", {});
        return r.data;
    },
};

export const examsPublicApi = {
    getMockExams: async (): Promise<NormalizedExamList<MockExamPublic>> => {
        const res = await api.get('/exams/mock-exams/');
        return parseMockExamPublicList(res.data, "GET /exams/mock-exams/");
    },
    getMockExam: async (id: number): Promise<MockExamPublic> => {
        const res = await api.get(`/exams/mock-exams/${id}/`);
        return parseMockExamPublicPayload(res.data, `GET /exams/mock-exams/${id}/`);
    },
    /** Pastpaper practice library only (standalone tests). Timed mocks: mock-exams APIs + /mock/:id. */
    getPracticeTests: async (): Promise<NormalizedExamList<PracticeTestPublic>> => {
        const res = await api.get('/exams/');
        return parsePracticeTestPublicList(res.data, "GET /exams/");
    },
    getPracticeTest: async (id: number): Promise<PracticeTestPublic> => {
        const res = await api.get(`/exams/${id}/`);
        return parsePracticeTestPublicPayload(res.data, `GET /exams/${id}/`);
    },
    getAttempts: async (): Promise<NormalizedExamList<TestAttempt>> => {
        const res = await api.get('/exams/attempts/');
        return parseTestAttemptList(res.data, "GET /exams/attempts/");
    },
    startTest: async (testId: number): Promise<TestAttempt> => {
        const res = await api.post('/exams/attempts/', { practice_test: testId });
        return parseTestAttemptApiPayload(res.data, "POST /exams/attempts/");
    },
    startModule: async (attemptId: number, moduleId: number): Promise<TestAttempt> => {
        const key = `start_module.${attemptId}.${moduleId}.${Date.now()}`;
        const res = await api.post(
            `/exams/attempts/${attemptId}/start_module/`,
            { module_id: moduleId },
            { headers: { "Idempotency-Key": key } },
        );
        return parseTestAttemptApiPayload(
            res.data,
            `POST /exams/attempts/${attemptId}/start_module/`,
        );
    },
    getAttemptStatus: async (attemptId: number): Promise<TestAttempt> => {
        // Canonical polling endpoint (new exam engine); fall back to legacy retrieve.
        try {
            const r = await api.get(`/exams/attempts/${attemptId}/status/`);
            return parseTestAttemptApiPayload(
                r.data,
                `GET /exams/attempts/${attemptId}/status/`,
            );
        } catch {
            const res = await api.get(`/exams/attempts/${attemptId}/`);
            return parseTestAttemptApiPayload(res.data, `GET /exams/attempts/${attemptId}/`);
        }
    },
    startAttemptEngine: async (attemptId: number, idempotencyKey?: string): Promise<TestAttempt> => {
        const res = await api.post(
            `/exams/attempts/${attemptId}/start/`,
            {},
            { headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : undefined },
        );
        return parseTestAttemptApiPayload(res.data, `POST /exams/attempts/${attemptId}/start/`);
    },
    resumeAttemptEngine: async (attemptId: number, idempotencyKey?: string): Promise<TestAttempt> => {
        const res = await api.post(
            `/exams/attempts/${attemptId}/resume/`,
            {},
            { headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : undefined },
        );
        return parseTestAttemptApiPayload(res.data, `POST /exams/attempts/${attemptId}/resume/`);
    },
    pauseAttempt: async (attemptId: number): Promise<TestAttempt> => {
        const res = await api.post(`/exams/attempts/${attemptId}/pause/`, {});
        return parseTestAttemptApiPayload(res.data, `POST /exams/attempts/${attemptId}/pause/`);
    },
    resumePauseAttempt: async (attemptId: number): Promise<TestAttempt> => {
        const res = await api.post(`/exams/attempts/${attemptId}/resume_pause/`, {});
        return parseTestAttemptApiPayload(res.data, `POST /exams/attempts/${attemptId}/resume_pause/`);
    },
    submitModule: async (attemptId: number, answers: object, flagged: number[] = [], options?: { idempotencyKey?: string; expectedVersionNumber?: number }): Promise<TestAttempt> => {
        const headers: Record<string, string> = {};
        if (options?.idempotencyKey) headers["Idempotency-Key"] = options.idempotencyKey;
        const payload: Record<string, unknown> = { answers, flagged };
        if (options?.expectedVersionNumber != null) payload.expected_version_number = options.expectedVersionNumber;
        const res = await api.post(`/exams/attempts/${attemptId}/submit_module/`, payload, { headers: Object.keys(headers).length ? headers : undefined });
        return parseTestAttemptApiPayload(
            res.data,
            `POST /exams/attempts/${attemptId}/submit_module/`,
        );
    },
    saveAttempt: async (attemptId: number, answers: object, flagged: number[] = [], options?: { idempotencyKey?: string; expectedVersionNumber?: number }): Promise<TestAttempt> => {
        const headers: Record<string, string> = {};
        if (options?.idempotencyKey) headers["Idempotency-Key"] = options.idempotencyKey;
        const payload: Record<string, unknown> = { answers, flagged };
        if (options?.expectedVersionNumber != null) payload.expected_version_number = options.expectedVersionNumber;
        const res = await api.post(`/exams/attempts/${attemptId}/save_attempt/`, payload, { headers: Object.keys(headers).length ? headers : undefined });
        return parseTestAttemptApiPayload(
            res.data,
            `POST /exams/attempts/${attemptId}/save_attempt/`,
        );
    },
    getResults: async (attemptId: number): Promise<TestAttempt> => {
        const res = await api.get(`/exams/attempts/${attemptId}/results/`);
        return parseTestAttemptApiPayload(res.data, `GET /exams/attempts/${attemptId}/results/`);
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    getReview: async (attemptId: number, moduleId?: number): Promise<any> => {
        const url = moduleId
            ? `/exams/attempts/${attemptId}/review/?module_id=${moduleId}`
            : `/exams/attempts/${attemptId}/review/`;
        const res = await api.get(url);
        // The review endpoint returns {questions, module_results, total_questions, ...}
        // — a different shape from TestAttempt. Return raw data.
        return res.data;
    },
    /**
     * Pastpaper section library: flattened list of standalone sections (one per
     * `PracticeTest`, subject MATH or READING_WRITING). Backed by the same
     * `/exams/` practice library as `getPracticeTests`; each row additionally
     * carries `collection_name` + `is_published`. Student visibility = published
     * OR assigned; only sections with questions and no mock_exam are returned.
     */
    getPastpaperSections: async (): Promise<PastpaperSection[]> => {
        const res = await api.get("/exams/");
        const raw = res.data;
        const arr = Array.isArray(raw) ? raw : Array.isArray(raw?.results) ? raw.results : [];
        return arr as PastpaperSection[];
    },
    /** Single pastpaper section. */
    getPastpaperSection: async (id: number): Promise<PastpaperSection> => {
        const res = await api.get(`/exams/${id}/`);
        return res.data as PastpaperSection;
    },
    /** Practice test pack student hub: published packs with questions. */
    getPracticeTestPacksStudent: async () => {
        const res = await api.get("/exams/practice-test-packs/");
        const raw = res.data;
        return Array.isArray(raw) ? raw : Array.isArray(raw?.results) ? raw.results : [];
    },
    /** Single practice test pack (includes sections). */
    getPracticeTestPackStudent: async (id: number) => {
        const res = await api.get(`/exams/practice-test-packs/${id}/`);
        return res.data;
    },
};

export type ScheduleEvent = {
    date: string; // YYYY-MM-DD
    type: "class" | "mock" | "midterm" | "assignment";
    title: string;
    sub?: string;
    time?: string;
    classroom_id?: number;
    mock_exam_id?: number;
    assignment_id?: number;
};

export const classesApi = {
    list: async (): Promise<NormalizedList<Classroom>> => {
        const r = await api.get('/classes/');
        return parseClassroomList(r.data, "GET /classes/");
    },
    /** Single classroom (member only); 404 if not enrolled or invalid id. */
    get: async (classId: number) => {
        const r = await api.get(`/classes/${classId}/`);
        return r.data;
    },
    create: async (data: { name: string; subject: 'ENGLISH' | 'MATH'; lesson_days: 'ODD' | 'EVEN'; lesson_time?: string; lesson_hours?: number; start_date?: string; room_number?: string; telegram_chat_id?: string; teacher?: number; max_students?: number; is_active?: boolean }) => {
        const r = await api.post('/classes/', data);
        return r.data;
    },
    update: async (classId: number, data: Record<string, unknown>) => {
        const r = await api.patch(`/classes/${classId}/`, data);
        return r.data;
    },
    /** Archive (soft) / restore a classroom — reuses is_active. */
    setArchived: async (classId: number, archived: boolean) => {
        const r = await api.patch(`/classes/${classId}/`, { is_active: !archived });
        return r.data;
    },
    // Materials (downloadable PDF/DOCX)
    listMaterials: async (classId: number) => {
        const r = await api.get(`/classes/${classId}/materials/`);
        return r.data;
    },
    uploadMaterial: async (classId: number, formData: FormData) => {
        const r = await api.post(`/classes/${classId}/materials/`, formData);
        return r.data;
    },
    deleteMaterial: async (classId: number, materialId: number) => {
        await api.delete(`/classes/${classId}/materials/${materialId}/`);
    },
    // Teacher: assign an existing interactive midterm to the whole classroom
    assignMidterm: async (classId: number, mockExamId: number) => {
        const r = await api.post(`/classes/${classId}/assign-midterm/`, { mock_exam_id: mockExamId });
        return r.data;
    },
    // Admin governance
    assignTeacher: async (classId: number, userId: number) => {
        const r = await api.post(`/classes/${classId}/assign-teacher/`, { user_id: userId });
        return r.data;
    },
    transferOwnership: async (classId: number, userId: number) => {
        const r = await api.post(`/classes/${classId}/transfer-ownership/`, { user_id: userId });
        return r.data;
    },
    // Results (read-only aggregation)
    midtermResults: async (classId: number) => {
        const r = await api.get(`/classes/${classId}/midterm-results/`);
        return r.data;
    },
    unifiedResults: async (classId: number, params?: { student?: number; type?: string; date_from?: string; date_to?: string }) => {
        const r = await api.get(`/classes/${classId}/results/`, { params });
        return r.data;
    },
    // Admin governance (admin/super_admin only)
    directory: async () => {
        const r = await api.get('/classes/directory/');
        return r.data;
    },
    governanceDelete: async (classId: number) => {
        await api.delete(`/classes/${classId}/governance-delete/`);
    },
    join: async (join_code: string) => {
        const r = await api.post('/classes/join/', { join_code });
        return r.data;
    },
    regenerateCode: async (classId: number) => {
        const r = await api.post(`/classes/${classId}/regenerate_code/`);
        return r.data;
    },
    people: async (classId: number) => {
        const r = await api.get(`/classes/${classId}/people/`);
        return r.data;
    },
    getLeaderboard: async (classId: number) => {
        const r = await api.get(`/classes/${classId}/leaderboard/`);
        return r.data;
    },
    /** Unified activity feed (posts, assignments, submissions), paginated. */
    getStream: async (classId: number, params?: { page?: number; page_size?: number }) => {
        const r = await api.get(`/classes/${classId}/stream/`, { params });
        return r.data;
    },
    /** Student-focused slices: your_assignments (with workflow_status), due_soon, recently_graded, new_posts. */
    getStudentWorkspace: async (classId: number) => {
        const r = await api.get(`/classes/${classId}/student-workspace/`);
        return r.data;
    },
    listComments: async (classId: number, targetType: 'post' | 'assignment', targetId: number) => {
        const r = await api.get(`/classes/${classId}/comments/`, {
            params: { target_type: targetType, target_id: targetId },
        });
        return r.data;
    },
    createComment: async (
        classId: number,
        data: { target_type: 'post' | 'assignment'; target_id: number; content: string; parent?: number | null },
    ) => {
        const r = await api.post(`/classes/${classId}/comments/`, data);
        return r.data;
    },
    /** Class teacher: mock exams + pastpaper tests for homework form (same visibility as portal lists). */
    getAssignmentOptions: async (classId: number) => {
        const r = await api.get(`/classes/${classId}/assignment-options/`);
        return r.data;
    },
    // Stream
    listPosts: async (classId: number) => {
        const r = await api.get(`/classes/${classId}/posts/`);
        return r.data;
    },
    createPost: async (classId: number, data: { content: string }) => {
        const r = await api.post(`/classes/${classId}/posts/`, data);
        return r.data;
    },
    // Assignments
    listAssignments: async (classId: number): Promise<NormalizedList<Assignment>> => {
        const r = await api.get(`/classes/${classId}/assignments/`);
        return parseAssignmentList(r.data, `GET /classes/${classId}/assignments/`);
    },
    createAssignment: async (classId: number, data: any, isFormData = false) => {
        const r = await api.post(`/classes/${classId}/assignments/`, data, isFormData ? {} : {});
        return r.data;
    },
    updateAssignment: async (
        classId: number,
        assignmentId: number,
        data: Record<string, unknown> | FormData,
        isFormData = false,
        options?: { replaceAttachments?: boolean },
    ) => {
        const r = await api.patch(`/classes/${classId}/assignments/${assignmentId}/`, data, {
            ...(isFormData ? {} : {}),
            ...(options?.replaceAttachments ? { params: { replace_attachments: '1' } } : {}),
        });
        return r.data;
    },
    deleteAssignment: async (classId: number, assignmentId: number) => {
        await api.delete(`/classes/${classId}/assignments/${assignmentId}/`);
    },
    submitAssignment: async (classId: number, assignmentId: number, payload: any, isFormData = true) => {
        const r = await axiosPostWith429Backoff(() =>
            api.post(
                `/classes/${classId}/assignments/${assignmentId}/submit/`,
                payload,
                isFormData ? {} : {},
            ),
        );
        return r.data;
    },
    getMySubmission: async (classId: number, assignmentId: number) => {
        const r = await api.get(`/classes/${classId}/assignments/${assignmentId}/my-submission/`);
        return r.data;
    },
    // Admin grading
    listSubmissions: async (classId: number, assignmentId: number) => {
        const r = await api.get(`/classes/${classId}/assignments/${assignmentId}/submissions/`);
        return r.data;
    },
    gradeSubmission: async (
        submissionId: number,
        payload: {
            grade?: string | number | null;
            score?: string | number | null;
            feedback?: string;
            expected_revision?: number;
        },
    ) => {
        const r = await api.post(`/classes/submissions/${submissionId}/grade/`, payload);
        return r.data;
    },
    /** Teacher returns work so the student can edit and resubmit (SUBMITTED or REVIEWED only). */
    returnSubmission: async (submissionId: number, payload?: { note?: string; expected_revision?: number }) => {
        const r = await api.post(`/classes/submissions/${submissionId}/return/`, payload ?? {});
        return r.data;
    },
    getSubmissionAuditLog: async (submissionId: number) => {
        const r = await api.get(`/classes/submissions/${submissionId}/audit-log/`);
        return r.data;
    },
    /**
     * Single fast endpoint: all assignments across every classroom the student is enrolled in.
     * Returns { count, items: Assignment[] } with `workflow_status`, `assessment_homework`,
     * `classroom_id`, `classroom_name` fields populated server-side.
     * Replaces the N+1 pattern of calling listAssignments per classroom.
     */
    myAssignments: async (): Promise<{ count: number; items: Assignment[] }> => {
        const r = await api.get('/classes/my-assignments/');
        const data = r.data as { count?: number; items?: unknown[] };
        return {
            count: data.count ?? 0,
            items: (data.items ?? []) as Assignment[],
        };
    },
    /** Student lessons calendar: class meetings + mock/midterm + assignment due dates in a date range. */
    mySchedule: async (from: string, to: string): Promise<{ from: string; to: string; events: ScheduleEvent[] }> => {
        const r = await api.get('/classes/my-schedule/', { params: { from, to } });
        const data = r.data as { from?: string; to?: string; events?: ScheduleEvent[] };
        return { from: data.from ?? from, to: data.to ?? to, events: data.events ?? [] };
    },
    /**
     * Teacher/admin: intervention signals for a classroom.
     * Returns overdue_students, inactive_students, low_score_students, completion_summary, class_stats.
     */
    getInterventions: async (classId: number) => {
        const r = await api.get(`/classes/${classId}/interventions/`);
        return r.data;
    },
};

export const examsAdminApi = {
    // Users
    getUsers: async () => { const r = await api.get('/users/'); return r.data; },
    createUser: async (data: object) => { const r = await api.post('/users/create/', data); return r.data; },
    updateUser: async (id: number, data: object) => { const r = await api.patch(`/users/${id}/update/`, data); return r.data; },
    deleteUser: async (id: number) => { await api.delete(`/users/${id}/delete/`); },

    listExamDatesAdmin: async () => {
        const r = await api.get('/users/admin/exam-dates/');
        return r.data;
    },
    createExamDate: async (data: {
        exam_date: string;
        label?: string;
        is_active?: boolean;
        sort_order?: number;
    }) => {
        const r = await api.post('/users/admin/exam-dates/', data);
        return r.data;
    },
    updateExamDate: async (
        id: number,
        data: Partial<{ exam_date: string; label: string; is_active: boolean; sort_order: number }>
    ) => {
        const r = await api.patch(`/users/admin/exam-dates/${id}/`, data);
        return r.data;
    },
    deleteExamDate: async (id: number) => {
        await api.delete(`/users/admin/exam-dates/${id}/`);
    },

    // Mock Exams (top-level grouping)
    getMockExams: async () => {
        const r = await api.get('/exams/admin/mock-exams/');
        return unwrapAdminList<AdminListEntity>(r.data);
    },
    getMidtermResults: async (examId: number) => {
        const r = await api.get(`/exams/admin/mock-exams/${examId}/results/`);
        return r.data;
    },
    createMockExam: async (data: object) => { const r = await api.post('/exams/admin/mock-exams/', data); return r.data; },
    updateMockExam: async (id: number, data: object) => { const r = await api.patch(`/exams/admin/mock-exams/${id}/`, data); return r.data; },
    deleteMockExam: async (id: number) => { await api.delete(`/exams/admin/mock-exams/${id}/`); },
    addTestToExam: async (examId: number, subject: string, label: string = '', formType: string = 'INTERNATIONAL') => {
        const r = await api.post(`/exams/admin/mock-exams/${examId}/add_test/`, { subject, label, form_type: formType });
        return r.data;
    },
    removeTestFromExam: async (examId: number, testId: number) => {
        const r = await api.delete(`/exams/admin/mock-exams/${examId}/remove_test/`, { data: { test_id: testId } });
        return r.data;
    },
    assignStudentsToExam: async (examId: number, userIds: number[]) => {
        const r = await api.post(`/exams/admin/mock-exams/${examId}/assign_users/`, { user_ids: userIds });
        return r.data;
    },
    publishMockExam: async (examId: number) => {
        const r = await api.post(`/exams/admin/mock-exams/${examId}/publish/`);
        return r.data;
    },
    unpublishMockExam: async (examId: number) => {
        const r = await api.post(`/exams/admin/mock-exams/${examId}/unpublish/`);
        return r.data;
    },
    bulkAssignStudents: async (
        examIds: number[],
        userIds: number[],
        assignmentType: string = 'FULL',
        formType?: string,
        practiceTestIds?: number[],
        clientContext?: Record<string, unknown>
    ): Promise<Record<string, unknown>> => {
        const payload: Record<string, unknown> = {
            exam_ids: examIds,
            user_ids: userIds,
            assignment_type: assignmentType,
        };
        if (formType) payload.form_type = formType;
        if (practiceTestIds?.length) payload.practice_test_ids = practiceTestIds;
        if (clientContext && Object.keys(clientContext).length) payload.client_context = clientContext;
        const res = await api.post('/exams/bulk_assign/', payload);
        return parseBulkAssignResponse(res.data, "POST /exams/bulk_assign/");
    },

    listBulkAssignmentHistory: async (): Promise<NormalizedList<BulkAssignmentDispatch>> => {
        const r = await api.get('/exams/assignments/history/');
        return parseBulkAssignmentHistoryList(r.data, "GET /exams/assignments/history/");
    },

    rerunBulkAssignmentDispatch: async (dispatchId: number) => {
        const r = await api.post(`/exams/assignments/history/${dispatchId}/rerun/`);
        return r.data;
    },

    // Standalone pastpaper sections (each a PracticeTest; the PastpaperPack grouping was removed).
    getStandaloneSections: async (): Promise<AdminPastpaperSection[]> => {
        const r = await api.get('/exams/admin/tests/', { params: { standalone: '1' } });
        return unwrapAdminList<AdminPastpaperSection>(r.data);
    },
    createSection: async (data: {
        subject: 'READING_WRITING' | 'MATH';
        title?: string;
        collection_name?: string;
        label?: string;
        form_type?: 'INTERNATIONAL' | 'US';
        practice_date?: string | null;
    }): Promise<AdminPastpaperSection> => {
        const r = await api.post('/exams/admin/tests/', { mock_exam: null, ...data });
        return r.data as AdminPastpaperSection;
    },
    updateSection: async (id: number, data: Record<string, unknown>): Promise<AdminPastpaperSection> => {
        const r = await api.patch(`/exams/admin/tests/${id}/`, data);
        return r.data as AdminPastpaperSection;
    },
    deleteSection: async (id: number) => {
        await api.delete(`/exams/admin/tests/${id}/`);
    },
    publishSection: async (id: number): Promise<AdminPastpaperSection> => {
        const r = await api.post(`/exams/admin/tests/${id}/publish/`);
        return r.data as AdminPastpaperSection;
    },
    unpublishSection: async (id: number): Promise<AdminPastpaperSection> => {
        const r = await api.post(`/exams/admin/tests/${id}/unpublish/`);
        return r.data as AdminPastpaperSection;
    },

    // Practice Test Packs (custom user-created, distinct from pastpapers)
    getPracticeTestPacks: async () => {
        const r = await api.get('/exams/admin/practice-test-packs/');
        const raw = r.data;
        const items = Array.isArray(raw) ? raw : Array.isArray(raw?.results) ? raw.results : [];
        return { items, count: items.length };
    },
    createPracticeTestPack: async (data: object) => {
        const r = await api.post('/exams/admin/practice-test-packs/', data);
        return r.data;
    },
    getPracticeTestPack: async (id: number) => {
        const r = await api.get(`/exams/admin/practice-test-packs/${id}/`);
        return r.data;
    },
    updatePracticeTestPack: async (id: number, data: object) => {
        const r = await api.patch(`/exams/admin/practice-test-packs/${id}/`, data);
        return r.data;
    },
    deletePracticeTestPack: async (id: number) => {
        await api.delete(`/exams/admin/practice-test-packs/${id}/`);
    },
    publishPracticeTestPack: async (id: number) => {
        const r = await api.post(`/exams/admin/practice-test-packs/${id}/publish/`);
        return r.data;
    },
    unpublishPracticeTestPack: async (id: number) => {
        const r = await api.post(`/exams/admin/practice-test-packs/${id}/unpublish/`);
        return r.data;
    },
    addPracticeTestPackSection: async (packId: number, subject: 'READING_WRITING' | 'MATH') => {
        const r = await api.post(`/exams/admin/practice-test-packs/${packId}/add_section/`, { subject });
        return r.data;
    },

    getPracticeTestsAdmin: async (standaloneOnly?: boolean) => {
        const r = await api.get('/exams/admin/tests/', {
            params: standaloneOnly ? { standalone: '1' } : undefined,
        });
        return unwrapAdminList<AdminListEntity>(r.data);
    },
    createPracticeTest: async (data: Record<string, unknown>) => {
        const r = await api.post('/exams/admin/tests/', { mock_exam: null, ...data });
        return r.data;
    },
    updatePracticeTest: async (id: number, data: object) => {
        const r = await api.patch(`/exams/admin/tests/${id}/`, data);
        return r.data;
    },
    deletePracticeTest: async (id: number) => {
        await api.delete(`/exams/admin/tests/${id}/`);
    },

    // Modules
    getModules: async (testId: number) => { const r = await api.get(`/exams/admin/tests/${testId}/modules/`); return r.data; },
    updateModule: async (testId: number, moduleId: number, data: object) => { const r = await api.patch(`/exams/admin/tests/${testId}/modules/${moduleId}/`, data); return r.data; },

    // Questions
    getQuestions: async (testId: number, moduleId: number) => { const r = await api.get(`/exams/admin/tests/${testId}/modules/${moduleId}/questions/`); return r.data; },
    getQuestion: async (testId: number, moduleId: number, questionId: number) => { const r = await api.get(`/exams/admin/tests/${testId}/modules/${moduleId}/questions/${questionId}/`); return r.data; },
    createQuestion: async (testId: number, moduleId: number, data: FormData | object, isFormData = false) => {
        // Let axios set multipart boundary; a bare Content-Type breaks file uploads.
        const r = await api.post(`/exams/admin/tests/${testId}/modules/${moduleId}/questions/`, data, isFormData ? {} : {});
        return r.data;
    },
    updateQuestion: async (testId: number, moduleId: number, questionId: number, data: FormData | object, isFormData = false) => {
        const r = await api.patch(`/exams/admin/tests/${testId}/modules/${moduleId}/questions/${questionId}/`, data, isFormData ? {} : {});
        return r.data;
    },
    deleteQuestion: async (testId: number, moduleId: number, questionId: number) => {
        await api.delete(`/exams/admin/tests/${testId}/modules/${moduleId}/questions/${questionId}/`);
    },
    reorderQuestion: async (testId: number, moduleId: number, questionId: number, action: 'up' | 'down') => {
        const r = await api.post(`/exams/admin/tests/${testId}/modules/${moduleId}/questions/${questionId}/reorder/`, { action });
        return r.data;
    },
    /**
     * Atomically reorder all questions in a module in one round-trip.
     * ``orderedIds`` must be the complete list of question IDs for the module in the desired order.
     */
    reorderQuestionsBulk: async (testId: number, moduleId: number, orderedIds: number[]) => {
        const r = await api.post(
            `/exams/admin/tests/${testId}/modules/${moduleId}/questions/bulk-reorder/`,
            { ordered_ids: orderedIds },
        );
        return r.data;
    },
};

export const vocabularyApi = {
    listWords: async (params?: { q?: string; difficulty?: number; part_of_speech?: string }) => {
        const r = await api.get("/vocabulary/words/", { params });
        return r.data;
    },
    getDaily: async (params?: { target?: number }) => {
        const r = await api.get("/vocabulary/daily/", { params });
        return r.data;
    },
    review: async (payload: { word_id: number; result: "correct" | "wrong" }) => {
        const r = await api.post("/vocabulary/review/", payload);
        return r.data;
    },
    adminListWords: async () => {
        const r = await api.get("/vocabulary/admin/words/");
        return r.data;
    },
    adminCreateWord: async (payload: {
        word: string;
        meaning?: string;
        example?: string;
        part_of_speech?: string;
        difficulty?: number;
    }) => {
        const r = await api.post("/vocabulary/admin/words/", payload);
        return r.data;
    },
    adminUpdateWord: async (
        id: number,
        payload: Partial<{
            word: string;
            meaning: string;
            example: string;
            part_of_speech: string;
            difficulty: number;
        }>,
    ) => {
        const r = await api.patch(`/vocabulary/admin/words/${id}/`, payload);
        return r.data;
    },
    adminDeleteWord: async (id: number) => {
        await api.delete(`/vocabulary/admin/words/${id}/`);
    },
};

export const assessmentsAdminApi = {
    adminListSets: async (params?: { subject?: "math" | "english"; category?: string; limit?: number; offset?: number }) => {
        const r = await api.get("/assessments/admin/sets/", { params });
        return r.data;
    },
    adminCreateSet: async (payload: {
        subject: "math" | "english";
        category?: string;
        title: string;
        description?: string;
        is_active?: boolean;
    }) => {
        const r = await api.post("/assessments/admin/sets/", payload);
        return r.data;
    },
    adminUpdateSet: async (
        id: number,
        payload: Partial<{
            subject: "math" | "english";
            category: string;
            title: string;
            description: string;
            is_active: boolean;
        }>,
    ) => {
        const r = await api.patch(`/assessments/admin/sets/${id}/`, payload);
        return r.data;
    },
    adminGetSet: async (id: number) => {
        const r = await api.get(`/assessments/admin/sets/${id}/`);
        return r.data;
    },
    adminCreateQuestion: async (
        setId: number,
        payload: {
            order?: number;
            prompt: string;
            question_type: "multiple_choice" | "short_text" | "numeric" | "boolean";
            choices?: any[];
            correct_answer?: any;
            grading_config?: Record<string, unknown>;
            points?: number;
            is_active?: boolean;
        },
    ) => {
        const r = await api.post(`/assessments/admin/sets/${setId}/questions/`, payload);
        return r.data;
    },
    adminUpdateQuestion: async (
        id: number,
        payload: Partial<{
            order: number;
            prompt: string;
            question_type: "multiple_choice" | "short_text" | "numeric" | "boolean";
            choices: any[];
            correct_answer: any;
            grading_config: Record<string, unknown>;
            points: number;
            is_active: boolean;
            question_image: File | null;
            clear_question_image: boolean;
        }> | FormData,
    ) => {
        const isFormData = payload instanceof FormData;
        const r = await api.patch(`/assessments/admin/questions/${id}/`, payload, isFormData ? {} : {});
        return r.data;
    },
    adminDeleteQuestion: async (id: number) => {
        await api.delete(`/assessments/admin/questions/${id}/`);
    },
    assignHomework: async (
        payload: {
            classroom_id: number;
            set_id: number;
            title?: string;
            instructions?: string;
            due_at?: string | null;
        },
        idempotencyKey?: string,
    ) => {
        const r = await api.post("/assessments/homework/assign/", payload, {
            headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : undefined,
        });
        return r.data;
    },
};

export default api;
