# Tenancy and isolation

Tenant scope is explicit at the request or background-job boundary. Code that
reads or writes tenant-owned data must either construct a repository with a
`tenant_id` or enter `tenant_scope(...)`; a missing context raises
`TenantContextError` rather than running an unscoped query.

`tenant_memberships` is the first tenant-owned table. Its migration enables and
forces PostgreSQL row-level security and checks the transaction-local
`app.tenant_id` setting for both reads and writes. Repository methods also add
the same `tenant_id` predicate, so local SQLite tests and a misconfigured RLS
connection still fail closed at the application layer.

The database setting is applied with `set_config(..., true)`, which limits it to
the current transaction and prevents tenant identity leaking through a pooled
connection. Future tenant-owned tables must carry `tenant_id`, enable the same
policy shape, and set the context before querying. `users` and `tenants` are
global identity/organization roots: they remain available for login, tenant
resolution, and bootstrap, while authenticated application services must verify
membership before exposing tenant data.
