import type { LoginInput } from "@support-agent/api-client";
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

interface BrowserLoginInput extends LoginInput {
  complete_social_link?: boolean;
}

export async function POST(request: NextRequest): Promise<NextResponse> {
  const crossSite = sameOriginError(request);
  if (crossSite) return crossSite;
  let completeSocialLink = false;
  try {
    const browserPayload = (await request.json()) as BrowserLoginInput;
    completeSocialLink = browserPayload.complete_social_link === true;
    const payload: LoginInput = {
      email: browserPayload.email,
      password: browserPayload.password,
      ...(browserPayload.organization_slug
        ? { organization_slug: browserPayload.organization_slug }
        : {}),
    };
    const challenge = await serverApi.login(payload, authClientHeaders(request));
    const response = NextResponse.json(pendingAuthResponse(challenge), { status: 202 });
    clearAuthCookies(response);
    if (!completeSocialLink) clearSocialLinkCookie(response);
    setPendingAuthCookie(response, challenge);
    return response;
  } catch (error) {
    const response = apiErrorResponse(error);
    if (!completeSocialLink) clearSocialLinkCookie(response);
    return response;
  }
}

