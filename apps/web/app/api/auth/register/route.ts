import type { RegisterInput } from "@support-agent/api-client";
import { NextResponse, type NextRequest } from "next/server";

import {
  apiErrorResponse,
  authClientHeaders,
  clearAuthCookies,
  clearSocialLinkCookie,
  pendingAuthResponse,
  sameOriginError,
  serverApi,
  setPendingAuthCookie,
} from "@/lib/server-auth";

export async function POST(request: NextRequest): Promise<NextResponse> {
  const crossSite = sameOriginError(request);
  if (crossSite) return crossSite;
  try {
    const payload = (await request.json()) as RegisterInput;
    const challenge = await serverApi.register(payload, authClientHeaders(request));
    const response = NextResponse.json(pendingAuthResponse(challenge), { status: 202 });
    clearAuthCookies(response);
    clearSocialLinkCookie(response);
    setPendingAuthCookie(response, challenge);
    return response;
  } catch (error) {
    return apiErrorResponse(error);
  }
}

