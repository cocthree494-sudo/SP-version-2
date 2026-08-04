import type { RegisterInput } from "@support-agent/api-client";
import { NextResponse, type NextRequest } from "next/server";

import { apiErrorResponse, serverApi, setAuthCookies } from "@/lib/server-auth";

export async function POST(request: NextRequest): Promise<NextResponse> {
  try {
    const payload = (await request.json()) as RegisterInput;
    const tokens = await serverApi.register(payload);
    const response = NextResponse.json({ ok: true }, { status: 201 });
    setAuthCookies(response, tokens);
    return response;
  } catch (error) {
    return apiErrorResponse(error);
  }
}

