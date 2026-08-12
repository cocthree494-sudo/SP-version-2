import type { SocialProvider } from "@support-agent/api-client";
import { NextResponse, type NextRequest } from "next/server";

import { apiErrorResponse, serverApi, setAuthCookies } from "@/lib/server-auth";

const providers = new Set<SocialProvider>(["google", "microsoft", "github"]);

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ provider: string }> },
): Promise<NextResponse> {
  const { provider } = await context.params;
  if (!providers.has(provider as SocialProvider)) {
    return NextResponse.json({ detail: "This sign-in provider is not available." }, { status: 404 });
  }
  const code = request.nextUrl.searchParams.get("code");
  const state = request.nextUrl.searchParams.get("state");
  if (!code || !state) {
    return NextResponse.redirect(new URL("/login?oauth_error=invalid_callback", request.url));
  }
  try {
    const result = await serverApi.socialCallback(provider as SocialProvider, { code, state });
    if (result.status === "authenticated" && result.access_token && result.refresh_token) {
      const response = NextResponse.redirect(new URL("/dashboard", request.url));
      setAuthCookies(response, {
        access_token: result.access_token,
        refresh_token: result.refresh_token,
        token_type: "bearer",
        expires_in: result.expires_in ?? 900,
      });
      return response;
    }
    if (result.status === "organization_required" && result.continuation_token) {
      return NextResponse.redirect(
        new URL(`/register?social_token=${encodeURIComponent(result.continuation_token)}`, request.url),
      );
    }
    if (result.status === "organization_selection_required" && result.continuation_token) {
      return NextResponse.redirect(
        new URL(`/login?social_select=${encodeURIComponent(result.continuation_token)}`, request.url),
      );
    }
    if (result.status === "account_link_required" && result.continuation_token) {
      return NextResponse.redirect(
        new URL(`/login?social_link=${encodeURIComponent(result.continuation_token)}`, request.url),
      );
    }
    return NextResponse.redirect(new URL("/login?oauth_error=incomplete", request.url));
  } catch (error) {
    const response = apiErrorResponse(error);
    if (response.status >= 400) {
      return NextResponse.redirect(new URL("/login?oauth_error=failed", request.url));
    }
    return response;
  }
}
