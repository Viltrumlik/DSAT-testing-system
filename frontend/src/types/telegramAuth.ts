/**
 * Telegram OIDC login result (https://core.telegram.org/bots/telegram-login).
 *
 * The new SDK at https://telegram.org/js/telegram-login.js returns an id_token JWT
 * signed by oauth.telegram.org. Backend verifies it against the JWKS endpoint.
 * The decoded ``user`` is convenience for client UI only — never trust it without
 * round-tripping the id_token through the server.
 */
export type TelegramOIDCUser = {
  /** OIDC subject: Telegram numeric user id as a string. */
  sub: string;
  iss: string;
  aud: string;
  exp: number;
  iat: number;
  /** Display name (full name). */
  name?: string;
  /** Telegram @handle without @. */
  preferred_username?: string;
  picture?: string;
  phone_number?: string;
};

export type TelegramOIDCResult = {
  /** JWT signed by oauth.telegram.org. Send this to the backend for verification. */
  id_token: string;
  /** Decoded claims for client-side display. Untrusted until backend verifies id_token. */
  user?: TelegramOIDCUser;
  error?: string;
};
