# Critical-path end-to-end coverage

T-060 adds Playwright specs under `tests/e2e` for the complete tenant slice:

- registration, bot creation, file/website/manual ingestion, background-ready
  polling, a grounded playground answer with citations, widget key creation, and
  anonymous Shadow DOM widget chat;
- a second-tenant negative request against the first tenant's bot;
- deterministic BYOK UI lifecycle covering write-only submission, masking,
  verification, explicit platform fallback selection, rotation, re-verification,
  immediate revocation, and preserved fallback mode.

The browser BYOK spec intercepts only the provider-settings BFF endpoints so it
can remain credential-free and deterministic. The real encrypted custody,
cross-tenant API, tenant target resolution, revocation, tenant-only failure, and
fallback ordering remain covered by `apps/api/tests/test_provider_access.py`.
Together these cover the UI and backend boundaries without ever using a paid or
real tenant key.

## Running later

Install Chromium once with `npm run test:e2e:install`. Start PostgreSQL/Redis,
apply migrations, configure the restricted role, and set a public deterministic
`E2E_WEBSITE_URL` that the SSRF-safe crawler can reach. Configure the deterministic
LLM response to contain a valid `[1]` citation. Then run `npm run test:e2e`.

The Playwright web server starts API, worker, dashboard, and a test-only widget
host on `127.0.0.1:4174`; the production widget bundle is built first. Traces,
screenshots, videos, and the HTML report go under ignored `output/playwright*`
paths. Per the user's instruction, T-060 authors this coverage but does not run
the full browser flow during the implementation batch.
