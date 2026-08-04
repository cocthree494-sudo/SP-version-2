import {
  ApiError,
  createApiClient,
  type TokenPairResponse,
} from "@support-agent/api-client";
import { NextResponse } from "next/server";

export const ACCESS_COOKIE = "sa_access_token";
export const REFRESH_COOKIE = "sa_refresh_token";

export const apiBaseUrl =
  process.env.API_INTERNAL_URL ??
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  "http://127.0.0.1:8000";

export const serverApi = createApiClient(apiBaseUrl);

const secureCookies = process.env.NODE_ENV === "production";

export function setAuthCookies(
  response: NextResponse,
  tokens: TokenPairResponse,
): void {
  response.cookies.set(ACCESS_COOKIE, tokens.access_token, {
    httpOnly: true,
    sameSite: "lax",
    secure: secureCookies,
    path: "/",
    maxAge: tokens.expires_in,
  });
  response.cookies.set(REFRESH_COOKIE, tokens.refresh_token, {
    httpOnly: true,
    sameSite: "lax",
    secure: secureCookies,
    path: "/",
    maxAge: 60 * 60 * 24 * 30,
  });
}

export function clearAuthCookies(response: NextResponse): void {
  for (const name of [ACCESS_COOKIE, REFRESH_COOKIE]) {
    response.cookies.set(name, "", {
      httpOnly: true,
      sameSite: "lax",
      secure: secureCookies,
      path: "/",
      maxAge: 0,
    });
  }
}

export function apiErrorResponse(error: unknown): NextResponse {
  if (error instanceof ApiError) {
    const status = error.status >= 400 && error.status < 500 ? error.status : 502;
    return NextResponse.json({ detail: error.detail }, { status });
  }
  return NextResponse.json(
    { detail: "The authentication service is temporarily unavailable." },
    { status: 502 },
  );
}
