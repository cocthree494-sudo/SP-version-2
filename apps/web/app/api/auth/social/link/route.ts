import type { SocialAuthLinkInput } from "@support-agent/api-client";
import { NextResponse, type NextRequest } from "next/server";

import { apiErrorResponse, serverApi, ACCESS_COOKIE } from "@/lib/server-auth";

export async function POST(request: NextRequest): Promise<NextResponse> {
  const accessToken = request.cookies.get(ACCESS_COOKIE)?.value;
  if (!accessToken) return NextResponse.json({ detail: "No active session" }, { status: 401 });
  try {
    const payload = (await request.json()) as SocialAuthLinkInput;
    await serverApi.socialLink(accessToken, payload);
    return NextResponse.json({ ok: true });
  } catch (error) {
    return apiErrorResponse(error);
  }
}
