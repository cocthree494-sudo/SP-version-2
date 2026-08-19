import { ApiError, type SocialProvider } from "@support-agent/api-client";
import { NextResponse, type NextRequest } from "next/server";

import {
  apiErrorResponse,
  clearPendingAuthCookies,
  publicRequestUrl,
  safeNextPath,
  serverApi,
  setOAuthFlowCookies,
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
  const nextPath = safeNextPath(request.nextUrl.searchParams.get("next"));
  if (nextPath?.startsWith("/admin") && provider !== "google") {
    return NextResponse.json({ detail: "Admin access supports Google sign-in only." }, { status: 404 });
  }
  const organizationSlug = request.nextUrl.searchParams.get("organization_slug") ?? undefined;
  try {
    const result = await serverApi.socialStart(provider as SocialProvider, {
      mode,
      ...(organizationSlug ? { organization_slug: organizationSlug } : {}),
    }, nextPath?.startsWith("/admin") ? { "X-Relay-Admin-Flow": "1" } : undefined);
    const response = NextResponse.redirect(result.authorization_url);
    clearPendingAuthCookies(response);
    setOAuthFlowCookies(response, mode, nextPath);
    return response;
  } catch (error) {
    if (error instanceof ApiError && error.status === 503) {
      const authUrl = publicRequestUrl(request, mode === "register" ? "/register" : "/login");
      authUrl.searchParams.set("oauth_error", "provider_unavailable");
      authUrl.searchParams.set("provider", provider);
      if (nextPath) authUrl.searchParams.set("next", nextPath);
      return NextResponse.redirect(authUrl);
    }
    return apiErrorResponse(error);
  }
}
