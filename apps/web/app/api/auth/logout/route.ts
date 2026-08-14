import { NextResponse, type NextRequest } from "next/server";

import {
  clearAuthCookies,
  clearPendingAuthCookies,
  sameOriginError,
} from "@/lib/server-auth";

export async function POST(request: NextRequest): Promise<NextResponse> {
  const crossSite = sameOriginError(request);
  if (crossSite) return crossSite;
  const response = NextResponse.json({ ok: true });
  clearAuthCookies(response);
  clearPendingAuthCookies(response);
  return response;
}
