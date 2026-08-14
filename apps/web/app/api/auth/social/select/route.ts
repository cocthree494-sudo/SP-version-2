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

interface SocialSelectionInput {
  organization_slug: string;
}

export async function POST(request: NextRequest): Promise<NextResponse> {
  const crossSite = sameOriginError(request);
  if (crossSite) return crossSite;
  const continuationToken = request.cookies.get(SOCIAL_CONTINUATION_COOKIE)?.value;
  if (!continuationToken) {
    return NextResponse.json({ detail: "The organization selection request expired. Start again." }, { status: 410 });
  }
  try {
    const payload = (await request.json()) as SocialSelectionInput;
    const challenge = await serverApi.socialSelect(
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
