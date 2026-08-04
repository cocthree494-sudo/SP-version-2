import type { LoginInput } from "@support-agent/api-client";
import { NextResponse, type NextRequest } from "next/server";

import { apiErrorResponse, serverApi, setAuthCookies } from "@/lib/server-auth";

export async function POST(request: NextRequest): Promise<NextResponse> {
  try {
    const payload = (await request.json()) as LoginInput;
    const tokens = await serverApi.login(payload);
    const response = NextResponse.json({ ok: true });
    setAuthCookies(response, tokens);
    return response;
  } catch (error) {
    return apiErrorResponse(error);
  }
}

