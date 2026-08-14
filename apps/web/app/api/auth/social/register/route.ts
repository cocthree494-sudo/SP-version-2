import { NextResponse, type NextRequest } from "next/server";

import {
  SOCIAL_CONTINUATION_COOKIE,
  apiErrorResponse,
  authClientHeaders,
  clearAuthCookies,
  clearSocialContinuationCookie,
  pendingAuthResponse,
  sameOriginError,
  serverApi,
  setPendingAuthCookie,
} from "@/lib/server-auth";

interface SocialRegistrationInput {
  organization_name?: string;
  organization_slug?: string;
}

export async function POST(request: NextRequest): Promise<NextResponse> {
  const crossSite = sameOriginError(request);
  if (crossSite) return crossSite;
  const continuationToken = request.cookies.get(SOCIAL_CONTINUATION_COOKIE)?.value;
  if (!continuationToken) {
    return NextResponse.json({ detail: "The social registration request expired. Start again." }, { status: 410 });
  }
  try {
    const payload = (await request.json()) as SocialRegistrationInput;
    const challenge = await serverApi.socialRegister(
      { continuation_token: continuationToken, ...payload },
      authClientHeaders(request),
    );
    const response = NextResponse.json(pendingAuthResponse(challenge), { status: 202 });
    clearAuthCookies(response);
    clearSocialContinuationCookie(response);
    setPendingAuthCookie(response, challenge);
    return response;
  } catch (error) {
    const response = apiErrorResponse(error);
    clearSocialContinuationCookie(response);
    return response;
  }
}
