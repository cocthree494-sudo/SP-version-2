# Dashboard authentication and shell

The Next.js application exposes the public landing page, registration and login forms, and a protected tenant dashboard under `/dashboard`.

## Browser authentication boundary

The browser never receives or stores API tokens in JavaScript-accessible storage. Login and registration post to same-origin Next.js route handlers, which call the FastAPI authentication endpoints and store the returned access and refresh tokens in `HttpOnly`, `SameSite=Lax` cookies. Secure cookies are enabled in production.

`GET /api/auth/session` validates the access token through `/v1/me`. If it has expired, the route rotates the refresh token, replaces both cookies, and then returns the current user and tenant context. Invalid sessions clear both cookies. The client authentication provider exposes only the current user, tenant, role, and session state.

The dashboard shell renders a loading state until session resolution completes and redirects anonymous users to `/login?next=...`. After authentication, only safe same-origin paths beginning with one `/` are accepted as a return target; external or protocol-relative redirects fall back to `/dashboard`.

## Organization context and responsive behavior

The `/v1/me` response supplies the active tenant and membership role displayed in the workspace switcher. Phase 1 supports the tenant bound to the authenticated token; multi-workspace switching is intentionally outside this task.

The shell includes accessible focus styles, route loading/error states, a responsive fixed sidebar, and a modal-style mobile navigation drawer. Motion is minimized when the operating system requests reduced motion.

## Configuration

- `API_INTERNAL_URL` is the server-only FastAPI URL used by Next.js route handlers.
- `NEXT_PUBLIC_API_BASE_URL` remains browser-visible configuration for future non-secret public calls.
- API credentials and tokens must never be placed in `NEXT_PUBLIC_*`, local storage, or session storage.

For local development, start FastAPI on `127.0.0.1:8000` and Next.js on `127.0.0.1:3000`. Registration creates the first organization and owner membership through the existing FastAPI bootstrap transaction.

## Verification

T-050 was inspected in a real browser at desktop and 390-pixel mobile widths. The landing, login, registration, unauthenticated dashboard redirect, authenticated tenant shell, and mobile navigation drawer were inspected. Because Docker/PostgreSQL/Redis were unavailable in the inspection environment, the authenticated visual state used a deterministic browser-only mock of `/api/auth/session`; the actual token rotation and tenancy behavior remain covered by backend authentication tests.
