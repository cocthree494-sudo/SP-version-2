import type { SocialProvider } from "@support-agent/api-client";
import { NextResponse, type NextRequest } from "next/server";

import {
  apiErrorResponse,
  authClientHeaders,
  clearPendingAuthCookies,
  publicRequestUrl,
  serverApi,
  setPendingAuthCookie,
  setSocialContinuationCookie,
  setSocialLinkCookie,
} from "@/lib/server-auth";

const providers = new Set<SocialProvider>(["google", "microsoft", "github"]);

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ provider: string }> },
): Promise<NextResponse> {
  const { provider } = await context.params;
  if (!providers.has(provider as SocialProvider)) {
    return NextResponse.json({ detail: "This sign-in provider is not available." }, { status: 404 });
  }
  const code = request.nextUrl.searchParams.get("code");
  const state = request.nextUrl.searchParams.get("state");
  if (!code || !state) {
    return NextResponse.redirect(new URL("/login?oauth_error=invalid_callback", request.url));
  }
  try {
    const result = await serverApi.socialCallback(
      provider as SocialProvider,
      { code, state },
      authClientHeaders(request),
    );
    if (result.status === "otp_required" && result.challenge_id) {
      const loginUrl = publicRequestUrl(request, "/login");
      loginUrl.searchParams.set("otp", "1");
      const response = NextResponse.redirect(loginUrl);
      clearPendingAuthCookies(response);
      setPendingAuthCookie(response, {
        status: "otp_required",
        challenge_id: result.challenge_id,
        email_hint: result.email_hint ?? "your email",
        expires_in: result.expires_in ?? 600,
        resend_after: result.resend_after ?? 60,
      });
      return response;
    }
    if (result.status === "organization_required" && result.continuation_token) {
      const registerUrl = publicRequestUrl(request, "/register");
      registerUrl.searchParams.set("social", "register");
      const response = NextResponse.redirect(registerUrl);
      clearPendingAuthCookies(response);
      setSocialContinuationCookie(response, result.continuation_token);
      return response;
    }
    if (result.status === "organization_selection_required" && result.continuation_token) {
      const loginUrl = publicRequestUrl(request, "/login");
      loginUrl.searchParams.set("social", "select");
      const response = NextResponse.redirect(loginUrl);
      clearPendingAuthCookies(response);
      setSocialContinuationCookie(response, result.continuation_token);
      return response;
    }
    if (result.status === "account_link_required" && result.continuation_token) {
      const loginUrl = publicRequestUrl(request, "/login");
      loginUrl.searchParams.set("social", "link");
      const response = NextResponse.redirect(loginUrl);
      clearPendingAuthCookies(response);
      setSocialLinkCookie(response, result.continuation_token);
      return response;
    }
    const loginUrl = publicRequestUrl(request, "/login");
    loginUrl.searchParams.set("oauth_error", "incomplete");
    return NextResponse.redirect(loginUrl);
  } catch (error) {
    const response = apiErrorResponse(error);
    if (response.status >= 400) {
      const loginUrl = publicRequestUrl(request, "/login");
      loginUrl.searchParams.set("oauth_error", "failed");
      return NextResponse.redirect(loginUrl);
    }
    return response;
  }
}
