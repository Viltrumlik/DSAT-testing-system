"use client";

import type { TelegramOIDCResult } from "@/types/telegramAuth";

export type { TelegramOIDCResult };

type Props = {
    /**
     * Server-side OAuth start URL (e.g. ``/api/users/telegram/start/``).
     * Returned by ``GET /api/users/telegram/config/``. The server redirects to oauth.telegram.org,
     * Telegram redirects back to ``/api/users/telegram/callback/``, the server sets JWT cookies and
     * redirects to ``next`` — so this is a full-page navigation, no popup, no callback.
     */
    startUrl?: string | null;
    /** Optional next path to land on after successful login. Defaults to "/". */
    next?: string;
    label?: string;
    /** Optional click hook (analytics). */
    onClick?: () => void;
    /**
     * Kept for backward compatibility. The OIDC code flow does the auth on the server, so this
     * callback is NOT invoked — server cookies do the work and the page is redirected.
     */
    onAuth?: (result: TelegramOIDCResult) => void;
    /** @deprecated kept for typing migration; no longer used in the code flow. */
    clientId?: number | string | null;
};

/**
 * Telegram OIDC Login button (authorization-code flow, server-mediated).
 * https://core.telegram.org/bots/telegram-login
 *
 * Clicking navigates to ``/api/users/telegram/start/?next=<path>`` which redirects the
 * browser to oauth.telegram.org. After approval, Telegram redirects back to
 * ``/api/users/telegram/callback/`` where the server exchanges the auth code for an id_token,
 * verifies it against the JWKS, upserts the user, sets HttpOnly JWT cookies, and lands on ``next``.
 */
export default function TelegramLoginButton({ startUrl, next, label, onClick }: Props) {
    if (!startUrl) return null;
    const target = `${startUrl}${next ? `?next=${encodeURIComponent(next)}` : ""}`;

    return (
        <a
            href={target}
            onClick={onClick}
            className="inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-full bg-[#2AABEE] hover:bg-[#229ED9] text-white font-semibold text-sm shadow-sm transition-colors no-underline"
            aria-label="Sign in with Telegram"
        >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                <path d="M12 0a12 12 0 1 0 0 24 12 12 0 0 0 0-24Zm5.43 8.18-1.81 8.53c-.14.61-.5.76-1.01.47l-2.79-2.06-1.35 1.3c-.15.15-.28.28-.56.28l.2-2.85 5.16-4.66c.22-.2-.05-.31-.35-.11l-6.38 4.01-2.75-.86c-.6-.19-.61-.6.13-.89l10.74-4.14c.5-.18.94.12.77.98Z" />
            </svg>
            {label || "Log in with Telegram"}
        </a>
    );
}
