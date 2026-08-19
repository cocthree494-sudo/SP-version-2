import { ApiError, type SocialProvider } from "@support-agent/api-client";
import { NextResponse, type NextRequest } from "next/server";

import {
  apiErrorResponse,
  authClientHeaders,
  clearOAuthFlowCookies,
  clearPendingAuthCookies,
  OAUTH_ADMIN_COOKIE,
  OAUTH_MODE_COOKIE,
  OAUTH_NEXT_COOKIE,
  publicRequestUrl,
  safeNextPath,
  serverApi,
  setPendingAuthCookie,
  setSocialContinuationCookie,
  setSocialLinkCookie,
} from "@/lib/server-auth";

const providers = new Set<SocialProvider>(["google", "microsoft", "github"]);

function preserveNext(url: URL, nextPath: string | null): URL {
  if (nextPath) url.searchParams.set("next", nextPath);
  return url;
}

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ provider: string }> },
): Promise<NextResponse> {
  const { provider } = await context.params;
  if (!providers.has(provider as SocialProvider)) {
    return NextResponse.json({ detail: "This sign-in provider is not available." }, { status: 404 });
  }
  const requestedMode = request.cookies.get(OAUTH_MODE_COOKIE)?.value === "register"
    ? "register"
    : "login";
  const nextPath = safeNextPath(request.cookies.get(OAUTH_NEXT_COOKIE)?.value);
  if (request.cookies.get(OAUTH_ADMIN_COOKIE)?.value === "1" && provider !== "google") {
    return NextResponse.json({ detail: "Admin access supports Google sign-in only." }, { status: 404 });
  }
  const code = request.nextUrl.searchParams.get("code");
  const state = request.nextUrl.searchParams.get("state");
  if (!code || !state) {
    const authUrl = preserveNext(
      publicRequestUrl(request, requestedMode === "register" ? "/register" : "/login"),
      nextPath,
    );
    authUrl.searchParams.set("oauth_error", "invalid_callback");
    const response = NextResponse.redirect(authUrl);
    clearOAuthFlowCookies(response);
    return response;
  }
  try {
    const result = await serverApi.socialCallback(
      provider as SocialProvider,
      { code, state },
      authClientHeaders(request),
    );
    if (result.status === "otp_required" && result.challenge_id) {
      const flow = result.flow ?? requestedMode;
      const otpUrl = preserveNext(
        publicRequestUrl(request, flow === "register" ? "/register" : "/login"),
        nextPath,
      );
      otpUrl.searchParams.set("otp", "1");
      const response = NextResponse.redirect(otpUrl);
      clearPendingAuthCookies(response);
      clearOAuthFlowCookies(response);
      setPendingAuthCookie(response, {
        status: "otp_required",
        challenge_id: result.challenge_id,
        email_hint: result.email_hint ?? "your email",
        flow,
        expires_in: result.expires_in ?? 600,
        resend_after: result.resend_after ?? 60,
      });
      return response;
    }
    if (result.status === "organization_required" && result.continuation_token) {
      const registerUrl = preserveNext(publicRequestUrl(request, "/register"), nextPath);
      registerUrl.searchParams.set("social", "register");
      const response = NextResponse.redirect(registerUrl);
      clearPendingAuthCookies(response);
      clearOAuthFlowCookies(response);
      setSocialContinuationCookie(response, result.continuation_token);
      return response;
    }
    if (result.status === "organization_selection_required" && result.continuation_token) {
      const loginUrl = preserveNext(publicRequestUrl(request, "/login"), nextPath);
      loginUrl.searchParams.set("social", "select");
      const response = NextResponse.redirect(loginUrl);
      clearPendingAuthCookies(response);
      clearOAuthFlowCookies(response);
      setSocialContinuationCookie(response, result.continuation_token);
      return response;
    }
    if (result.status === "account_link_required" && result.continuation_token) {
      const loginUrl = preserveNext(publicRequestUrl(request, "/login"), nextPath);
      loginUrl.searchParams.set("social", "link");
      const response = NextResponse.redirect(loginUrl);
      clearPendingAuthCookies(response);
      clearOAuthFlowCookies(response);
      setSocialLinkCookie(response, result.continuation_token);
      return response;
    }
    const authUrl = preserveNext(
      publicRequestUrl(request, requestedMode === "register" ? "/register" : "/login"),
      nextPath,
    );
    authUrl.searchParams.set("oauth_error", "incomplete");
    const response = NextResponse.redirect(authUrl);
    clearOAuthFlowCookies(response);
    return response;
  } catch (error) {
    const apiResponse = apiErrorResponse(error);
    if (apiResponse.status >= 400) {
      const isExistingAccount = error instanceof ApiError && error.status === 409;
      const authUrl = preserveNext(
        publicRequestUrl(
          request,
          isExistingAccount || requestedMode === "register" ? "/register" : "/login",
        ),
        nextPath,
      );
      authUrl.searchParams.set("oauth_error", isExistingAccount ? "account_exists" : "failed");
      authUrl.searchParams.set("provider", provider);
      const response = NextResponse.redirect(authUrl);
      clearPendingAuthCookies(response);
      clearOAuthFlowCookies(response);
      return response;
    }
    return apiResponse;
  }
}
