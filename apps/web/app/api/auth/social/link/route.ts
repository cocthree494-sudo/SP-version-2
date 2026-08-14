import { NextResponse, type NextRequest } from "next/server";

import {
  ACCESS_COOKIE,
  SOCIAL_LINK_COOKIE,
  apiErrorResponse,
  clearSocialLinkCookie,
  sameOriginError,
  serverApi,
} from "@/lib/server-auth";

export async function POST(request: NextRequest): Promise<NextResponse> {
  const crossSite = sameOriginError(request);
  if (crossSite) return crossSite;
  const accessToken = request.cookies.get(ACCESS_COOKIE)?.value;
  const continuationToken = request.cookies.get(SOCIAL_LINK_COOKIE)?.value;
  if (!accessToken) return NextResponse.json({ detail: "No active session" }, { status: 401 });
  if (!continuationToken) {
    return NextResponse.json({ detail: "The account-link request expired. Start again." }, { status: 410 });
  }
  try {
    await serverApi.socialLink(accessToken, { continuation_token: continuationToken });
    const response = NextResponse.json({ ok: true });
    clearSocialLinkCookie(response);
    return response;
  } catch (error) {
    const response = apiErrorResponse(error);
    clearSocialLinkCookie(response);
    return response;
  }
}
