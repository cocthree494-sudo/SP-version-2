import { ApiError } from "@support-agent/api-client";
import { NextResponse, type NextRequest } from "next/server";

import {
  PENDING_AUTH_COOKIE,
  SOCIAL_LINK_COOKIE,
  apiErrorResponse,
  clearPendingAuthCookies,
  sameOriginError,
  serverApi,
  setAuthCookies,
} from "@/lib/server-auth";

interface BrowserOtpVerifyInput {
  code?: string;
}

export async function POST(request: NextRequest): Promise<NextResponse> {
  const crossSite = sameOriginError(request);
  if (crossSite) return crossSite;
  const challengeId = request.cookies.get(PENDING_AUTH_COOKIE)?.value;
  if (!challengeId) {
    return NextResponse.json({ detail: "The verification request expired. Start again." }, { status: 410 });
  }

  try {
    const payload = (await request.json()) as BrowserOtpVerifyInput;
    const tokens = await serverApi.otpVerify({
      challenge_id: challengeId,
      code: payload.code ?? "",
    });
    let linkWarning: string | null = null;
    const socialLinkToken = request.cookies.get(SOCIAL_LINK_COOKIE)?.value;
    if (socialLinkToken) {
      try {
        await serverApi.socialLink(tokens.access_token, {
          continuation_token: socialLinkToken,
        });
      } catch {
        linkWarning = "You are signed in, but the social account was not linked. Start the social sign-in again to retry.";
      }
    }
    const response = NextResponse.json({ ok: true, link_warning: linkWarning });
    clearPendingAuthCookies(response);
    setAuthCookies(response, tokens);
    return response;
  } catch (error) {
    const response = apiErrorResponse(error);
    if (error instanceof ApiError && (error.status !== 400 || error.status >= 500)) {
      clearPendingAuthCookies(response);
    }
    return response;
  }
}
