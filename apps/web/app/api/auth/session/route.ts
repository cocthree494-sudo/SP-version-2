import { ApiError } from "@support-agent/api-client";
import { NextResponse, type NextRequest } from "next/server";

import {
  ACCESS_COOKIE,
  REFRESH_COOKIE,
  apiErrorResponse,
  clearAuthCookies,
  serverApi,
  setAuthCookies,
} from "@/lib/server-auth";

function unauthenticated(): NextResponse {
  const response = NextResponse.json({ detail: "No active session" }, { status: 401 });
  clearAuthCookies(response);
  return response;
}

export async function GET(request: NextRequest): Promise<NextResponse> {
  const accessToken = request.cookies.get(ACCESS_COOKIE)?.value;
  const refreshToken = request.cookies.get(REFRESH_COOKIE)?.value;
  if (!accessToken && !refreshToken) {
    return unauthenticated();
  }

  if (accessToken) {
    try {
      return NextResponse.json(await serverApi.me(accessToken));
    } catch (error) {
      if (!(error instanceof ApiError) || error.status !== 401) {
        return apiErrorResponse(error);
      }
    }
  }

  if (!refreshToken) {
    return unauthenticated();
  }
  try {
    const tokens = await serverApi.refresh(refreshToken);
    const me = await serverApi.me(tokens.access_token);
    const response = NextResponse.json(me);
    setAuthCookies(response, tokens);
    return response;
  } catch (error) {
    if (error instanceof ApiError && [401, 403].includes(error.status)) {
      return unauthenticated();
    }
    return apiErrorResponse(error);
  }
}

