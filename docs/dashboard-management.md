# Dashboard bot and knowledge management

T-051 adds tenant-facing bot CRUD and knowledge-source management under `/dashboard/bots` and `/dashboard/knowledge`.

## Authenticated API bridge

Dashboard code calls the same-origin `/api/backend/*` bridge. The bridge forwards requests only to the configured `API_INTERNAL_URL` under `/v1`, injects the tenant-bound access token from an `HttpOnly` cookie, rotates an expired session once through the refresh endpoint, and streams the upstream response back without exposing either token to browser JavaScript.

State-changing requests require the custom `X-Relay-Request: dashboard` header and reject a mismatched `Origin`. A cross-origin page cannot add this header without a successful CORS preflight, and the bridge does not grant cross-origin access. Request bodies are read with a strict configurable cap (`DASHBOARD_PROXY_MAX_BODY_BYTES`, 24 MiB by default) so a chunked request cannot make the BFF buffer unbounded data. The FastAPI upload endpoint still applies the authoritative file-size, MIME, signature, and tenant checks.

## Bot management

Owners and admins can create, edit, disable, and delete bots. Members receive the same tenant-scoped list but the mutation controls are hidden. The editor supports the configured language behavior and trusted system-policy boundary. Deletion uses an explicit alert dialog and explains that dependent credentials and knowledge are removed.

Each bot card links directly to the knowledge workspace with its bot identifier. The knowledge page validates the requested identifier against the tenant-scoped bot list before selecting it.

## Knowledge management

The knowledge workspace supports:

- drag/drop or file-picker upload for PDF, DOCX, TXT, and Markdown, including partial success reporting for multi-file batches;
- bounded website crawl configuration with page and depth limits;
- authoritative manual question/answer creation and editing;
- per-source ready, pending, processing, failed, and deleting states;
- visible safe error text and error reference codes;
- explicit deletion confirmation;
- four-second polling only while at least one source is in a transitional state.

Bot/source requests are always addressed through the existing tenant-authenticated API. Parsing, crawling, chunking, and embedding remain in the background ingestion worker rather than the Next.js or FastAPI request workers.

Widget appearance, exact-origin keys, preview, and generated installation
instructions live in the separate `/dashboard/widget` workspace and are
documented in `docs/widget.md`.

## Verification

Web lint and TypeScript checks pass. Browser inspection covered populated bot cards, bot creation dialog, file drop zone, website/manual forms, manual edit prefill, transitional and failed source states, source deletion confirmation, and the full 390-pixel mobile knowledge layout. The browser used deterministic same-origin API responses because local PostgreSQL/Redis/Docker were unavailable; backend API behavior and tenant isolation remain covered by the existing API suite.
