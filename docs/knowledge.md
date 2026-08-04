# Knowledge ingestion and retrieval

T-031 through T-036 implement the tenant-scoped knowledge path for files,
websites, manual Q&A, document versions, embeddings, and hybrid retrieval.

## Authenticated source API

- `POST /v1/bots/{bot_id}/sources/files` accepts multipart PDF, DOCX, TXT, or
  Markdown from owners/admins.
- `POST /v1/bots/{bot_id}/sources/websites` creates a bounded website crawl.
- `POST /v1/bots/{bot_id}/sources/manual` creates authoritative Q&A.
- `PATCH /v1/sources/{source_id}/manual` updates Q&A and queues a new version
  only when its question or answer changed.
- `GET /v1/bots/{bot_id}/sources` and `GET /v1/sources/{source_id}` expose
  status and safe source details to tenant members.
- `DELETE /v1/sources/{source_id}` removes stored raw/normalized objects and
  then cascades tenant-owned database records.

File uploads are streamed with a byte limit, sanitized display filename,
extension/MIME allow-list, and content signature checks. Storage paths use
generated source IDs, never client filenames. PDF and DOCX are signature-checked
at upload and fully parsed in the worker. DOCX archive paths, expansion size,
and compression ratios are bounded. TXT/Markdown require UTF-8.

## Worker pipeline

The ARQ worker loads raw input, extracts deterministic normalized UTF-8 text,
stores it, creates a staged document version, chunks on structural boundaries
with bounded token overlap, embeds in configured batches, and activates the new
version only after every chunk succeeds. The previous active version is merely
superseded, so failed re-ingestion cannot erase usable knowledge.

The deterministic embedding provider is the credential-free local/test default.
The provider interface and configured production adapter are described in
[Provider adapters](providers.md).

## Website safety

Website crawls enforce HTTP(S), standard ports, exact-host traversal, maximum
pages/depth/response bytes/redirects, canonical URL deduplication, content
checksum deduplication, robots rules, and bounded request delay. Every request
and redirect target is DNS-resolved and rejected when any address is loopback,
private, link-local, reserved, multicast, or otherwise non-global.

## Retrieval

`HybridRetrievalService` embeds a query and retrieves only active documents for
the explicit tenant and bot. PostgreSQL uses pgvector cosine candidates plus a
generated `tsvector`/GIN lexical candidate set. Reciprocal-rank fusion combines
the rankings, exact duplicate chunks are removed, and each result carries
source/document/title/URL/chunk/offset citation data. SQLite has a deterministic
portable fallback used for cross-tenant and evaluation fixtures.

Optional source and language filters repeat tenant scope on every joined table.
Sources being refreshed or holding a failed new attempt remain searchable when
they still have an active document version.
