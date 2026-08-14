import { ApiError } from "@support-agent/api-client";
import { NextResponse, type NextRequest } from "next/server";

import {
  PENDING_AUTH_COOKIE,
  apiErrorResponse,
  authClientHeaders,
  clearPendingAuthCookies,
  pendingAuthResponse,
  sameOriginError,
  serverApi,
  setPendingAuthCookie,
} from "@/lib/server-auth";

export async function POST(request: NextRequest): Promise<NextResponse> {
  const crossSite = sameOriginError(request);
  if (crossSite) return crossSite;
  const challengeId = request.cookies.get(PENDING_AUTH_COOKIE)?.value;
  if (!challengeId) {
    return NextResponse.json({ detail: "The verification request expired. Start again." }, { status: 410 });
  }

  try {
    const challenge = await serverApi.otpResend(
      { challenge_id: challengeId },
      authClientHeaders(request),
    );
    const response = NextResponse.json(pendingAuthResponse(challenge));
    setPendingAuthCookie(response, challenge);
    return response;
  } catch (error) {
    const response = apiErrorResponse(error);
    if (error instanceof ApiError && (error.status === 410 || error.status >= 500)) {
      clearPendingAuthCookies(response);
    }
    return response;
  }
}
