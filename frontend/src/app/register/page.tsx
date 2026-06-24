"use client";
import React, { useCallback, useEffect, useState } from "react";
import { authApi, usersApi } from "@/lib/api";
import { useRouter } from "next/navigation";
import { UserPlus, Sparkles, ShieldCheck, LineChart, User, Mail, Lock, Eye, EyeOff, Send } from "lucide-react";
import Link from "next/link";
import { type TelegramOIDCResult } from "@/components/TelegramLoginButton";
import { Button, Input, Field, Alert, Spinner } from "@/components/ui";

declare global {
    interface Window {
        google?: any;
    }
}

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

export default function RegisterPage() {
    const [firstName, setFirstName] = useState("");
    const [lastName, setLastName] = useState("");
    const [username, setUsername] = useState("");
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [error, setError] = useState("");
    const [loading, setLoading] = useState(false);
    const [showPw, setShowPw] = useState(false);
    const [googleReady, setGoogleReady] = useState(false);
    const router = useRouter();
    const [telegramCfg, setTelegramCfg] = useState<{ enabled: boolean; bot_username: string | null; client_id: string | null; start_url: string | null } | null>(null);

    useEffect(() => {
        usersApi
            .getTelegramWidgetConfig()
            .then(setTelegramCfg)
            .catch(() => setTelegramCfg({ enabled: false, bot_username: null, client_id: null, start_url: null }));
    }, []);

    const handleTelegramAuth = useCallback(
        async (result: TelegramOIDCResult) => {
            setLoading(true);
            setError("");
            try {
                await authApi.telegramAuth(result.id_token, true);
                router.push("/");
            } catch (err: unknown) {
                const ax = err as { response?: { data?: { detail?: string } } };
                setError(ax?.response?.data?.detail || "Telegram signup failed. Check your connection and try again.");
            } finally {
                setLoading(false);
            }
        },
        [router],
    );

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setLoading(true);
        setError("");
        if (firstName.trim().length < 3 || lastName.trim().length < 3 || username.trim().length < 3) {
            setError("First name, last name, and username must be at least 3 characters.");
            setLoading(false);
            return;
        }
        try {
            await authApi.register(firstName, lastName, username, email, password);
            // Auto login after registration
            await authApi.login(email, password);
            router.push("/");
        } catch (err: unknown) {
            const ax = err as { response?: { status?: number; data?: Record<string, unknown> }; code?: string; message?: string };
            let msg = "Registration failed. Please check your details.";
            if (!ax.response) {
                msg = ax.code === "ECONNABORTED" || ax.message?.includes("timeout")
                    ? "Request timed out. Check your connection and try again."
                    : "Cannot connect to the server. Check your internet connection.";
            } else if (ax.response.status === 429) {
                msg = "Too many attempts. Please wait a minute before trying again.";
            } else if (ax.response.data) {
                const d = ax.response.data;
                if (typeof d.detail === "string") msg = d.detail;
                else if (Array.isArray(d.email)) msg = d.email[0] as string;
                else if (Array.isArray(d.username)) msg = d.username[0] as string;
                else if (Array.isArray(d.first_name)) msg = d.first_name[0] as string;
                else if (Array.isArray(d.last_name)) msg = d.last_name[0] as string;
                else if (Array.isArray(d.password)) msg = d.password[0] as string;
                else if (typeof d === "object" && Object.keys(d).length > 0) {
                    const firstError = Object.values(d)[0];
                    if (Array.isArray(firstError)) msg = firstError[0] as string;
                }
            }
            setError(msg);
        } finally {
            setLoading(false);
        }
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
                    callback: async (response: { credential?: string }) => {
                        if (!response?.credential) return;
                        try {
                            await authApi.googleAuth(response.credential, undefined, true);
                            router.push("/");
                        } catch (err: unknown) {
                            const ax = err as { response?: { data?: { detail?: string } } };
                            setError(ax?.response?.data?.detail || "Google sign up failed. Check your connection and try again.");
                        }
                    },
                });
                setGoogleReady(true);
            } catch (err) {
                console.warn("Google Sign-Up init failed", err);
            }
        };

        tryInit();
        return () => {
            cancelled = true;
            if (pollTimer !== null) window.clearTimeout(pollTimer);
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [router]);

    return (
        <div className="ds-app flex min-h-screen bg-background text-foreground">
            {/* Brand panel — desktop only */}
            <aside
                className="authbrand relative hidden w-[44%] max-w-xl flex-col justify-between overflow-hidden p-12 text-white lg:flex"
                style={{ background: "linear-gradient(160deg,#2a68c0,#1f4d9a)" }}
            >
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
                    <h2 className="text-[44px] font-extrabold leading-[1.05] tracking-tight">Real past papers. Real scores. Real progress.</h2>
                    <p className="mt-[18px] max-w-[440px] text-[16px] font-medium leading-relaxed opacity-[0.82]">
                        Take a full-length diagnostic, get your predicted score, and focus on the exact domains where you&apos;re losing points.
                    </p>
                    <ul className="mt-[34px] flex flex-col gap-4">
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
                        <h1 className="ds-h2 mt-3">Create account</h1>
                    </div>

                    <div className="mb-6 hidden lg:block">
                        <h1 className="ds-h1">Create your account</h1>
                        <p className="ds-small mt-1">Join the MasterSAT program.</p>
                    </div>

                    <form className="flex flex-col gap-4" onSubmit={handleSubmit}>
                        {error ? <Alert tone="danger">{error}</Alert> : null}

                        <div className="grid grid-cols-2 gap-3">
                            <Field label="First name" htmlFor="firstName">
                                <Input id="firstName" required placeholder="John" value={firstName} onChange={(e) => setFirstName(e.target.value)} disabled={loading} autoComplete="given-name" />
                            </Field>
                            <Field label="Last name" htmlFor="lastName">
                                <Input id="lastName" required placeholder="Doe" value={lastName} onChange={(e) => setLastName(e.target.value)} disabled={loading} autoComplete="family-name" />
                            </Field>
                        </div>
                        <Field label="Username" htmlFor="username">
                            <Input id="username" required placeholder="johndoe123" value={username} onChange={(e) => setUsername(e.target.value)} disabled={loading} autoComplete="username" leftIcon={<User className="h-4 w-4" />} />
                        </Field>
                        <Field label="Email address" htmlFor="email-address">
                            <Input id="email-address" type="email" required placeholder="name@example.com" value={email} onChange={(e) => setEmail(e.target.value)} disabled={loading} autoComplete="email" leftIcon={<Mail className="h-4 w-4" />} />
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
                                autoComplete="new-password"
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

                        <Button type="submit" loading={loading} fullWidth size="lg" rightIcon={<UserPlus />} className="!bg-[#2a68c0] hover:!bg-[#21539e]">
                            Create account
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
                    </form>

                    <p className="mt-6 text-center text-sm text-muted-foreground">
                        Already have an account?{" "}
                        <Link href="/login" className="font-bold text-[#2a68c0] hover:underline">
                            Sign in
                        </Link>
                    </p>
                </div>
            </main>
        </div>
    );
}
