import { ApiError } from "@support-agent/api-client";
import { NextResponse, type NextRequest } from "next/server";

import {
  PENDING_AUTH_COOKIE,
  apiErrorResponse,
  clearPendingAuthCookies,
  pendingAuthResponse,
  serverApi,
} from "@/lib/server-auth";

export async function GET(request: NextRequest): Promise<NextResponse> {
  const challengeId = request.cookies.get(PENDING_AUTH_COOKIE)?.value;
  if (!challengeId) return new NextResponse(null, { status: 204 });

  try {
    const challenge = await serverApi.otpStatus({ challenge_id: challengeId });
    return NextResponse.json(pendingAuthResponse(challenge));
  } catch (error) {
    const response = apiErrorResponse(error);
    if (error instanceof ApiError && [400, 410, 429].includes(error.status)) {
      clearPendingAuthCookies(response);
    }
    return response;
  }
}
