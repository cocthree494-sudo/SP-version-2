import {
  ApiError,
  createApiClient,
  type AuthChallengeResponse,
  type PendingAuthResponse,
  type TokenPairResponse,
} from "@support-agent/api-client";
import { isIP } from "node:net";
import { NextResponse, type NextRequest } from "next/server";

export const ACCESS_COOKIE = "sa_access_token";
export const REFRESH_COOKIE = "sa_refresh_token";
export const PENDING_AUTH_COOKIE = "sa_pending_auth";
export const SOCIAL_CONTINUATION_COOKIE = "sa_social_continuation";
export const SOCIAL_LINK_COOKIE = "sa_social_link";

export const apiBaseUrl =
  process.env.API_INTERNAL_URL ??
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  "http://127.0.0.1:8000";

export const serverApi = createApiClient(apiBaseUrl);

/** Build redirects from the browser-facing host, not the container bind host. */
export function publicRequestUrl(request: NextRequest, pathname: string): URL {
  const forwardedHost = request.headers.get("x-forwarded-host")?.split(",", 1)[0]?.trim();
  const host = forwardedHost || request.headers.get("host");
  if (!host) return new URL(pathname, request.url);

  const forwardedProto = request.headers.get("x-forwarded-proto")?.split(",", 1)[0]?.trim();
  const protocol = forwardedProto === "http" || forwardedProto === "https"
    ? forwardedProto
    : new URL(request.url).protocol.replace(":", "");
  return new URL(pathname, `${protocol}://${host}`);
}

const secureCookies = process.env.NODE_ENV === "production";

const privateCookieOptions = {
  httpOnly: true,
  sameSite: "lax" as const,
  secure: secureCookies,
  path: "/",
};

export function setAuthCookies(
  response: NextResponse,
  tokens: TokenPairResponse,
): void {
  response.cookies.set(ACCESS_COOKIE, tokens.access_token, {
    ...privateCookieOptions,
    maxAge: tokens.expires_in,
  });
  response.cookies.set(REFRESH_COOKIE, tokens.refresh_token, {
    ...privateCookieOptions,
    maxAge: 60 * 60 * 24 * 30,
  });
}

export function pendingAuthResponse(challenge: AuthChallengeResponse): PendingAuthResponse {
  return {
    status: "otp_required",
    email_hint: challenge.email_hint,
    expires_in: challenge.expires_in,
    resend_after: challenge.resend_after,
  };
}

export function setPendingAuthCookie(
  response: NextResponse,
  challenge: AuthChallengeResponse,
): void {
  response.cookies.set(PENDING_AUTH_COOKIE, challenge.challenge_id, {
    ...privateCookieOptions,
    maxAge: Math.max(1, challenge.expires_in),
  });
}

export function setSocialContinuationCookie(
  response: NextResponse,
  token: string,
): void {
  response.cookies.set(SOCIAL_CONTINUATION_COOKIE, token, {
    ...privateCookieOptions,
    maxAge: 10 * 60,
  });
}

export function setSocialLinkCookie(response: NextResponse, token: string): void {
  response.cookies.set(SOCIAL_LINK_COOKIE, token, {
    ...privateCookieOptions,
    maxAge: 10 * 60,
  });
}

export function clearPendingAuthCookies(response: NextResponse): void {
  for (const name of [PENDING_AUTH_COOKIE, SOCIAL_CONTINUATION_COOKIE, SOCIAL_LINK_COOKIE]) {
    response.cookies.set(name, "", {
      ...privateCookieOptions,
      maxAge: 0,
    });
  }
}

export function clearSocialContinuationCookie(response: NextResponse): void {
  response.cookies.set(SOCIAL_CONTINUATION_COOKIE, "", {
    ...privateCookieOptions,
    maxAge: 0,
  });
}

export function clearSocialLinkCookie(response: NextResponse): void {
  response.cookies.set(SOCIAL_LINK_COOKIE, "", {
    ...privateCookieOptions,
    maxAge: 0,
  });
}

export function clearAuthCookies(response: NextResponse): void {
  for (const name of [ACCESS_COOKIE, REFRESH_COOKIE]) {
    response.cookies.set(name, "", {
      ...privateCookieOptions,
      maxAge: 0,
    });
  }
}

export function authClientHeaders(request: NextRequest): HeadersInit {
  const candidates = [
    request.headers.get("cf-connecting-ip"),
    request.headers.get("x-real-ip"),
    request.headers.get("x-forwarded-for")?.split(",", 1)[0]?.trim(),
  ];
  for (const candidate of candidates) {
    if (candidate && isIP(candidate) !== 0) {
      return { "X-Relay-Client-IP": candidate };
    }
  }
  return {};
}

export function sameOriginError(request: NextRequest): NextResponse | null {
  if (request.headers.get("sec-fetch-site") === "cross-site") {
    return NextResponse.json({ detail: "Cross-site authentication requests are not allowed." }, { status: 403 });
  }
  const origin = request.headers.get("origin");
  if (origin && origin !== publicRequestUrl(request, "/").origin) {
    return NextResponse.json({ detail: "Cross-site authentication requests are not allowed." }, { status: 403 });
  }
  return null;
}

export function apiErrorResponse(error: unknown): NextResponse {
  if (error instanceof ApiError) {
    const status = error.status >= 400 && error.status < 500 ? error.status : 502;
    const response = NextResponse.json({ detail: error.detail }, { status });
    if (error.retryAfter !== null) {
      response.headers.set("Retry-After", String(error.retryAfter));
    }
    return response;
  }
  return NextResponse.json(
    { detail: "The authentication service is temporarily unavailable." },
    { status: 502 },
  );
}
