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

Authentication adds two constrained cases to this model. `refresh_tokens` is
tenant-owned and uses both repository `tenant_id` predicates and the same
forced RLS policy as memberships. Its opaque credential carries a non-secret
tenant UUID prefix so the refresh request can establish that scope before
querying a hash.

Login necessarily occurs before a tenant is selected. After a password has
been verified, the auth-only membership repository sets transaction-local
`app.user_id` and queries with an exact `user_id` predicate. A SELECT-only RLS
policy permits that user to resolve their own memberships; it does not allow
cross-user reads or any membership write. Once one membership is selected,
the resulting access token is tenant-bound and protected endpoints verify that
membership again under normal tenant scope.
