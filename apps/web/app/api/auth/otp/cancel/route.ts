import { ApiError } from "@support-agent/api-client";
import { NextResponse, type NextRequest } from "next/server";

import {
  PENDING_AUTH_COOKIE,
  apiErrorResponse,
  clearPendingAuthCookies,
  sameOriginError,
  serverApi,
} from "@/lib/server-auth";

export async function POST(request: NextRequest): Promise<NextResponse> {
  const crossSite = sameOriginError(request);
  if (crossSite) return crossSite;
  const challengeId = request.cookies.get(PENDING_AUTH_COOKIE)?.value;
  if (challengeId) {
    try {
      await serverApi.otpCancel({ challenge_id: challengeId });
    } catch (error) {
      if (!(error instanceof ApiError) || error.status >= 500) {
        return apiErrorResponse(error);
      }
    }
  }
  const response = new NextResponse(null, { status: 204 });
  clearPendingAuthCookies(response);
  return response;
}
