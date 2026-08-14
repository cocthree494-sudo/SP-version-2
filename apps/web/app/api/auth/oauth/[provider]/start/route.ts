import { ApiError, type SocialProvider } from "@support-agent/api-client";
import { NextResponse, type NextRequest } from "next/server";

import {
  apiErrorResponse,
  clearPendingAuthCookies,
  publicRequestUrl,
  serverApi,
} from "@/lib/server-auth";

const providers = new Set<SocialProvider>(["google", "microsoft", "github"]);

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ provider: string }> },
): Promise<NextResponse> {
  const { provider } = await context.params;
  if (!providers.has(provider as SocialProvider)) {
    return NextResponse.json({ detail: "This sign-in provider is not available." }, { status: 404 });
  }
  const mode = request.nextUrl.searchParams.get("mode") === "register" ? "register" : "login";
  const organizationSlug = request.nextUrl.searchParams.get("organization_slug") ?? undefined;
  try {
    const result = await serverApi.socialStart(provider as SocialProvider, {
      mode,
      ...(organizationSlug ? { organization_slug: organizationSlug } : {}),
    });
    const response = NextResponse.redirect(result.authorization_url);
    clearPendingAuthCookies(response);
    return response;
  } catch (error) {
    if (error instanceof ApiError && error.status === 503) {
      const loginUrl = publicRequestUrl(request, "/login");
      loginUrl.searchParams.set("oauth_error", "provider_unavailable");
      loginUrl.searchParams.set("provider", provider);
      return NextResponse.redirect(loginUrl);
    }
    return apiErrorResponse(error);
  }
}
