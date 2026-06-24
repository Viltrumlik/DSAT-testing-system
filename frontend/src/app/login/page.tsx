"use client";
import React, { useCallback, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { authApi, usersApi } from "@/lib/api";
import { invalidateMe } from "@/hooks/useMe";
import { useRouter } from "next/navigation";
import { LogIn, RefreshCw, Sparkles, ShieldCheck, LineChart, Mail, Lock, Eye, EyeOff, Send } from "lucide-react";
import Link from "next/link";
import { type TelegramOIDCResult } from "@/components/TelegramLoginButton";
import type { AuthNoticeRecord } from "@/lib/auth/authTabSync";
import { consumeAuthNotice } from "@/lib/auth/authTabSync";
import { Button, Input, Field, Alert, Spinner, type AlertTone } from "@/components/ui";

declare global {
    interface Window {
        google?: any;
    }
}

function classifyLoginError(err: unknown): { message: string; retryable: boolean } {
    const ax = err as { response?: { status?: number; data?: { detail?: string; missing_fields?: string[] } }; code?: string; message?: string };
    const status = ax.response?.status;
    const detail = ax.response?.data?.detail;

    if (!ax.response) {
        if (ax.code === "ECONNABORTED" || ax.message?.includes("timeout")) {
            return { message: "Request timed out. Please check your connection and try again.", retryable: true };
        }
        return { message: "Cannot connect to the server. Check your internet connection and try again.", retryable: true };
    }
    if (status === 401 || status === 400) {
        return { message: detail || "The email or password you entered is incorrect.", retryable: false };
    }
    if (status === 403) {
        return { message: detail || "Your account has been restricted. Contact support.", retryable: false };
    }
    if (status === 429) {
        return { message: "Too many login attempts. Please wait a minute before trying again.", retryable: false };
    }
    if (status !== undefined && status >= 500) {
        return { message: "Server error. Please try again in a moment.", retryable: true };
    }
    return { message: detail || "Sign-in failed. Please try again.", retryable: true };
}

function getRedirectTarget(): string {
    const host = typeof window !== "undefined" ? window.location.hostname.toLowerCase() : "";
    if (host.startsWith("admin.")) return "/ops";
    if (host.startsWith("questions.")) return "/builder";
    return "/";
}

const NOTICE_COPY: Record<string, { tone: AlertTone; message: string }> = {
    EXPIRED: { tone: "warning", message: "Your session has expired. Please sign in again." },
    NO_SESSION: { tone: "info", message: "No active session found. Sign in to continue." },
    NETWORK: { tone: "info", message: "The network was interrupted while loading your profile. Sign in again to continue." },
    SERVER: { tone: "info", message: "The server could not validate your profile. Sign in again, or retry after a short wait." },
};

function GoogleGlyph() {
    return (
        <svg className="h-4 w-4" viewBox="0 0 24 24" aria-hidden>
            <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.76h3.56c2.08-1.92 3.28-4.74 3.28-8.09Z" />
            <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.56-2.76c-.98.66-2.23 1.06-3.72 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84A11 11 0 0 0 12 23Z" />
            <path fill="#FBBC05" d="M5.84 14.11a6.6 6.6 0 0 1 0-4.22V7.05H2.18a11 11 0 0 0 0 9.9l3.66-2.84Z" />
            <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.05l3.66 2.84C6.71 7.3 9.14 5.38 12 5.38Z" />
        </svg>
    );
}

export default function LoginPage() {
    const queryClient = useQueryClient();
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [error, setError] = useState("");
    const [isRetryable, setIsRetryable] = useState(false);
    const [loading, setLoading] = useState(false);
    const [rememberMe] = useState(true);
    const [showPw, setShowPw] = useState(false);
    const [forgotOpen, setForgotOpen] = useState(false);
    const [googleReady, setGoogleReady] = useState(false);
    const [googleCredential, setGoogleCredential] = useState("");
    const [googleMissing, setGoogleMissing] = useState<string[]>([]);
    const [googleProfile, setGoogleProfile] = useState({ first_name: "", last_name: "", username: "" });
    const router = useRouter();
    const [telegramCfg, setTelegramCfg] = useState<{
        enabled: boolean;
        bot_username: string | null;
        client_id: string | null;
        start_url: string | null;
    } | null>(null);
    const lastSubmitRef = useRef<(() => void) | null>(null);

    const [authRouteNotice, setAuthRouteNotice] = useState<AuthNoticeRecord | null>(null);

    useEffect(() => {
        const rec = consumeAuthNotice();
        if (rec) setAuthRouteNotice(rec);
    }, []);

    useEffect(() => {
        usersApi
            .getTelegramWidgetConfig()
            .then(setTelegramCfg)
            .catch(() => setTelegramCfg({ enabled: false, bot_username: null, client_id: null, start_url: null }));
    }, []);

    const completeLogin = useCallback(async () => {
        try {
            await usersApi.getMe().catch(() => null);
        } catch { /* identity probe is best-effort */ }
        void invalidateMe(queryClient);
        router.push(getRedirectTarget());
    }, [queryClient, router]);

    const handleSubmit = async (e?: React.FormEvent) => {
        e?.preventDefault();
        if (!email.trim() || !password) return;
        setLoading(true);
        setError("");
        setIsRetryable(false);
        lastSubmitRef.current = () => void handleSubmit();
        try {
            await authApi.login(email, password, rememberMe);
            await completeLogin();
        } catch (err: unknown) {
            const { message, retryable } = classifyLoginError(err);
            setError(message);
            setIsRetryable(retryable);
        } finally {
            setLoading(false);
        }
    };

    const handleTelegramAuth = useCallback(
        async (result: TelegramOIDCResult) => {
            setLoading(true);
            setError("");
            setIsRetryable(false);
            lastSubmitRef.current = () => void handleTelegramAuth(result);
            try {
                await authApi.telegramAuth(result.id_token, rememberMe);
                await completeLogin();
            } catch (err: unknown) {
                const { message, retryable } = classifyLoginError(err);
                setError(message);
                setIsRetryable(retryable);
            } finally {
                setLoading(false);
            }
        },
        [rememberMe, completeLogin],
    );

    const handleGoogleCredential = async (credential: string, profile?: { first_name?: string; last_name?: string; username?: string }) => {
        setLoading(true);
        setError("");
        setIsRetryable(false);
        lastSubmitRef.current = () => void handleGoogleCredential(credential, profile);
        try {
            await authApi.googleAuth(credential, profile, rememberMe);
            await completeLogin();
        } catch (err: unknown) {
            const ax = err as { response?: { data?: { missing_fields?: string[] } } };
            const missing = ax.response?.data?.missing_fields;
            if (Array.isArray(missing) && missing.length) {
                setGoogleCredential(credential);
                setGoogleMissing(missing);
                setError("Please complete missing profile fields to continue.");
                setIsRetryable(false);
            } else {
                const { message, retryable } = classifyLoginError(err);
                setError(message);
                setIsRetryable(retryable);
            }
        } finally {
            setLoading(false);
        }
    };

    const handleRetry = () => {
        if (lastSubmitRef.current) lastSubmitRef.current();
    };

    useEffect(() => {
        const clientId = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID;
        if (!clientId || clientId.includes("your-google-web-client-id")) return;

        let cancelled = false;
        let pollTimer: number | null = null;

        const tryInit = () => {
            if (cancelled) return;
            if (!window.google?.accounts?.id) {
                pollTimer = window.setTimeout(tryInit, 200);
                return;
            }
            try {
                window.google.accounts.id.initialize({
                    client_id: clientId,
                    callback: (response: { credential?: string }) => {
                        if (response?.credential) {
                            void handleGoogleCredential(response.credential);
                        }
                    },
                });
                setGoogleReady(true);
            } catch (err) {
                console.warn("Google Sign-In init failed", err);
            }
        };

        tryInit();
        return () => {
            cancelled = true;
            if (pollTimer !== null) window.clearTimeout(pollTimer);
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const notice = authRouteNotice?.reason ? NOTICE_COPY[authRouteNotice.reason] : null;

    return (
        <div className="ds-app flex min-h-screen bg-background text-foreground">
            {/* Brand panel — desktop only */}
            <aside
                className="authbrand relative hidden w-[44%] max-w-xl flex-col justify-between overflow-hidden p-12 text-white lg:flex"
                style={{ background: "linear-gradient(160deg,#2a68c0,#1f4d9a)" }}
            >
                {/* floating decorative shapes */}
                <span aria-hidden className="pointer-events-none absolute -right-[70px] -top-[50px] h-[280px] w-[280px] rounded-full bg-white/10" style={{ animation: "dz-floatA 14s ease-in-out infinite" }} />
                <span aria-hidden className="pointer-events-none absolute -bottom-[90px] right-[60px] h-[200px] w-[200px] bg-white/[0.08]" style={{ borderRadius: 44, animation: "dz-floatB 16s ease-in-out infinite" }} />
                <span aria-hidden className="pointer-events-none absolute bottom-[120px] -left-[60px] h-[150px] w-[150px] rounded-full border-[18px] border-white/[0.11]" style={{ animation: "dz-floatC 13s ease-in-out infinite" }} />
                <span aria-hidden className="pointer-events-none absolute left-[40px] top-[180px] h-4 w-4 rounded-[5px] bg-white/30" style={{ animation: "dz-floatD 11s ease-in-out infinite" }} />
                <span aria-hidden className="pointer-events-none absolute right-[120px] top-[90px] h-[60px] w-[60px] rounded-[18px] bg-white/[0.07]" style={{ animation: "dz-floatD 15s ease-in-out infinite" }} />
                <span aria-hidden className="pointer-events-none absolute -bottom-[40px] left-[140px] h-[120px] w-[120px] rounded-full border-[10px] border-white/[0.08]" style={{ animation: "dz-drift 40s linear infinite" }} />

                <div className="relative flex items-center gap-3">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src="/images/logo.png" alt="" className="h-12 w-auto object-contain" style={{ filter: "brightness(0) invert(1)" }} />
                    <p className="text-xl font-extrabold tracking-tight">MasterSAT</p>
                </div>

                <div className="relative max-w-md">
                    <h2 className="text-[44px] font-extrabold leading-[1.05] tracking-tight">Your digital SAT, mastered.</h2>
                    <ul className="mt-9 flex flex-col gap-4">
                        {[
                            { icon: LineChart, text: "Live readiness and score trends" },
                            { icon: Sparkles, text: "Classroom assessments and monthly midterm exams" },
                            { icon: ShieldCheck, text: "Real Exam environment" },
                        ].map(({ icon: Icon, text }) => (
                            <li key={text} className="flex items-center gap-3 text-[15px] font-medium">
                                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-white/15">
                                    <Icon className="h-4 w-4" />
                                </span>
                                {text}
                            </li>
                        ))}
                    </ul>
                </div>

                <p className="relative text-xs opacity-70">© {new Date().getFullYear()} MasterSAT Center</p>
            </aside>

            {/* Form panel */}
            <main className="flex flex-1 items-center justify-center px-5 py-10">
                <div className="w-full max-w-md">
                    <div className="mb-8 text-center lg:hidden">
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img src="/images/logo.png" alt="" className="mx-auto h-16 w-16 object-contain" />
                        <h1 className="ds-h2 mt-3">MasterSAT</h1>
                    </div>

                    <div className="mb-7 hidden lg:block">
                        <h1 className="text-[34px] font-extrabold tracking-tight text-foreground">Welcome back</h1>
                    </div>

                    <form className="flex flex-col gap-4" onSubmit={handleSubmit}>
                        {notice ? <Alert tone={notice.tone}>{notice.message}</Alert> : null}
                        {error ? (
                            <Alert tone="danger" title={error}>
                                {isRetryable ? (
                                    <button
                                        type="button"
                                        onClick={handleRetry}
                                        disabled={loading}
                                        className="ds-ring mt-1 inline-flex items-center gap-1.5 rounded-md text-xs font-bold underline disabled:opacity-50"
                                    >
                                        <RefreshCw className="h-3 w-3" /> Retry
                                    </button>
                                ) : null}
                            </Alert>
                        ) : null}

                        <Field label="Email or username" htmlFor="email-address">
                            <Input
                                id="email-address"
                                type="text"
                                required
                                placeholder="name@example.com or username"
                                value={email}
                                onChange={(e) => setEmail(e.target.value)}
                                disabled={loading}
                                autoComplete="username"
                                leftIcon={<Mail className="h-4 w-4" />}
                            />
                        </Field>
                        <Field label="Password" htmlFor="password">
                            <Input
                                id="password"
                                type={showPw ? "text" : "password"}
                                required
                                placeholder="••••••••"
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                                disabled={loading}
                                autoComplete="current-password"
                                leftIcon={<Lock className="h-4 w-4" />}
                                rightSlot={
                                    <button type="button" tabIndex={-1} aria-label={showPw ? "Hide password" : "Show password"}
                                        onClick={() => setShowPw((v) => !v)}
                                        className="ds-ring flex items-center justify-center rounded-md text-label-foreground hover:text-foreground">
                                        {showPw ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                                    </button>
                                }
                            />
                        </Field>

                        <div className="-mt-1 flex items-center justify-end">
                            <button type="button" onClick={() => setForgotOpen((v) => !v)} className="ds-ring rounded-md text-[13px] font-bold text-[#2a68c0] hover:underline">
                                Forgot password?
                            </button>
                        </div>
                        {forgotOpen ? (
                            <p className="-mt-2 text-[12px] text-muted-foreground">Ask your teacher or the MasterSAT center to reset your password.</p>
                        ) : null}

                        <Button type="submit" loading={loading} fullWidth size="lg" rightIcon={<LogIn />} className="!bg-[#2a68c0] hover:!bg-[#21539e]">
                            Sign in
                        </Button>

                        <div className="flex items-center gap-3 py-1">
                            <span className="h-px flex-1 bg-border" />
                            <span className="ds-overline">or</span>
                            <span className="h-px flex-1 bg-border" />
                        </div>

                        <div className="flex gap-3">
                            {googleReady ? (
                                <button
                                    type="button"
                                    onClick={() => { try { window.google?.accounts?.id?.prompt(); } catch { /* ignore */ } }}
                                    disabled={loading}
                                    className="ds-ring flex flex-1 items-center justify-center gap-2.5 rounded-xl border border-border bg-card px-3 py-3 text-sm font-bold text-foreground transition-all hover:-translate-y-0.5 hover:border-border-strong hover:shadow-card active:scale-[0.98] disabled:opacity-60"
                                >
                                    <GoogleGlyph /> Google
                                </button>
                            ) : null}
                            {telegramCfg?.enabled && telegramCfg.start_url ? (
                                <a
                                    href={`${telegramCfg.start_url}?next=${encodeURIComponent("/")}`}
                                    className="ds-ring flex flex-1 items-center justify-center gap-2.5 rounded-xl px-3 py-3 text-sm font-extrabold text-white transition-all hover:-translate-y-0.5 hover:shadow-[0_8px_20px_rgba(42,171,238,.4)] active:scale-[0.98]"
                                    style={{ background: "#2aabee" }}
                                >
                                    <Send className="h-4 w-4" /> Telegram
                                </a>
                            ) : telegramCfg === null ? (
                                <span className="flex flex-1 items-center justify-center py-3"><Spinner className="h-5 w-5 text-muted-foreground" /></span>
                            ) : null}
                        </div>

                        {googleMissing.length > 0 ? (
                            <div className="flex flex-col gap-3 pt-1">
                                {googleMissing.includes("first_name") ? (
                                    <Input
                                        placeholder="First name (min 3)"
                                        value={googleProfile.first_name}
                                        onChange={(e) => setGoogleProfile((p) => ({ ...p, first_name: e.target.value }))}
                                    />
                                ) : null}
                                {googleMissing.includes("last_name") ? (
                                    <Input
                                        placeholder="Last name (min 3)"
                                        value={googleProfile.last_name}
                                        onChange={(e) => setGoogleProfile((p) => ({ ...p, last_name: e.target.value }))}
                                    />
                                ) : null}
                                <Button type="button" variant="secondary" fullWidth onClick={() => handleGoogleCredential(googleCredential, googleProfile)}>
                                    Continue with Google profile
                                </Button>
                            </div>
                        ) : null}
                    </form>

                    <p className="mt-6 text-center text-sm text-muted-foreground">
                        Don&apos;t have an account?{" "}
                        <Link href="/register" className="font-bold text-[#2a68c0] hover:underline">
                            Register now
                        </Link>
                    </p>
                </div>
            </main>
        </div>
    );
}
