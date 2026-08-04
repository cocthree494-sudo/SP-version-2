import { NextResponse } from "next/server";

import { clearAuthCookies } from "@/lib/server-auth";

export async function POST(): Promise<NextResponse> {
  const response = NextResponse.json({ ok: true });
  clearAuthCookies(response);
  return response;
}
