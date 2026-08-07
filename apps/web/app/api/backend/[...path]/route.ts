import { ApiError } from "@support-agent/api-client";
import { NextResponse, type NextRequest } from "next/server";

import {
  ACCESS_COOKIE,
  REFRESH_COOKIE,
  apiBaseUrl,
  clearAuthCookies,
  serverApi,
  setAuthCookies,
} from "@/lib/server-auth";

interface RouteContext {
  params: Promise<{ path: string[] }>;
}

const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);
const DEFAULT_PROXY_BODY_MAX_BYTES = 24 * 1024 * 1024;

class ProxyBodyTooLargeError extends Error {}

function proxyBodyLimit(): number {
  const configured = Number(process.env.DASHBOARD_PROXY_MAX_BODY_BYTES);
  return Number.isSafeInteger(configured) && configured > 0
    ? configured
    : DEFAULT_PROXY_BODY_MAX_BYTES;
}

async function readBoundedBody(request: NextRequest): Promise<ArrayBuffer | undefined> {
  if (!request.body) return undefined;
  const limit = proxyBodyLimit();
  const declaredLength = Number(request.headers.get("content-length"));
  if (Number.isFinite(declaredLength) && declaredLength > limit) {
    throw new ProxyBodyTooLargeError();
  }

  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.byteLength;
    if (total > limit) {
      await reader.cancel();
      throw new ProxyBodyTooLargeError();
    }
    chunks.push(value);
  }
  const merged = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    merged.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return merged.buffer;
}

function responseHeaders(upstream: Response): Headers {
  const headers = new Headers();
  for (const name of ["content-type", "cache-control", "content-disposition", "x-request-id"]) {
    const value = upstream.headers.get(name);
    if (value) headers.set(name, value);
  }
  return headers;
}

function hasSameDashboardOrigin(request: NextRequest, origin: string | null): boolean {
  if (!origin) return true;
  try {
    const parsed = new URL(origin);
    const host = request.headers.get("host");
    const forwardedProtocol = request.headers.get("x-forwarded-proto")?.split(",", 1)[0]?.trim();
    const protocol = forwardedProtocol || request.nextUrl.protocol.replace(/:$/, "");
    return Boolean(host) && parsed.host === host && parsed.protocol === `${protocol}:`;
  } catch {
    return false;
  }
}

async function proxy(request: NextRequest, context: RouteContext): Promise<NextResponse> {
  if (!SAFE_METHODS.has(request.method)) {
    const relayHeader = request.headers.get("x-relay-request");
    const origin = request.headers.get("origin");
    if (relayHeader !== "dashboard" || !hasSameDashboardOrigin(request, origin)) {
      return NextResponse.json({ detail: "Invalid dashboard request" }, { status: 403 });
    }
  }

  const accessToken = request.cookies.get(ACCESS_COOKIE)?.value;
  const refreshToken = request.cookies.get(REFRESH_COOKIE)?.value;
  if (!accessToken && !refreshToken) {
    return NextResponse.json({ detail: "No active session" }, { status: 401 });
  }

  const { path } = await context.params;
  const encodedPath = path.map(encodeURIComponent).join("/");
  const targetUrl = `${apiBaseUrl}/v1/${encodedPath}${request.nextUrl.search}`;
  try {
    const body = SAFE_METHODS.has(request.method) ? undefined : await readBoundedBody(request);
    const send = (token: string) => {
      const headers = new Headers({
        Accept: request.headers.get("accept") ?? "application/json",
      });
      const contentType = request.headers.get("content-type");
      if (contentType) headers.set("Content-Type", contentType);
      headers.set("Authorization", `Bearer ${token}`);
      return fetch(targetUrl, {
        method: request.method,
        headers,
        body: body && body.byteLength > 0 ? body : undefined,
        cache: "no-store",
        redirect: "manual",
        signal: request.signal,
      });
    };

    let tokens = null;
    let upstream = accessToken ? await send(accessToken) : null;
    if ((!upstream || upstream.status === 401) && refreshToken) {
      tokens = await serverApi.refresh(refreshToken);
      upstream = await send(tokens.access_token);
    }
    if (!upstream) {
      const response = NextResponse.json({ detail: "No active session" }, { status: 401 });
      clearAuthCookies(response);
      return response;
    }

    const response = new NextResponse(upstream.body, {
      status: upstream.status,
      headers: responseHeaders(upstream),
    });
    if (tokens) setAuthCookies(response, tokens);
    if (upstream.status === 401) clearAuthCookies(response);
    return response;
  } catch (error) {
    if (error instanceof ProxyBodyTooLargeError) {
      return NextResponse.json({ detail: "Dashboard request body is too large" }, { status: 413 });
    }
    if (error instanceof ApiError && [401, 403].includes(error.status)) {
      const response = NextResponse.json({ detail: "No active session" }, { status: 401 });
      clearAuthCookies(response);
      return response;
    }
    return NextResponse.json(
      { detail: "The support API is temporarily unavailable." },
      { status: 502 },
    );
  }
}

export const GET = proxy;
export const POST = proxy;
export const PATCH = proxy;
export const PUT = proxy;
export const DELETE = proxy;
