"""Explicit tenant context and PostgreSQL row-level-security helpers."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_current_tenant_id: ContextVar[UUID | None] = ContextVar(
    "current_tenant_id",
    default=None,
)


class TenantContextError(RuntimeError):
    """Raised when tenant-owned work runs without an explicit tenant."""


def get_current_tenant_id() -> UUID:
    """Return the request/job tenant or fail closed when it is missing."""

    tenant_id = _current_tenant_id.get()
    if tenant_id is None:
        raise TenantContextError("A tenant context is required before accessing tenant-owned data")
    return tenant_id


def maybe_current_tenant_id() -> UUID | None:
    """Return the current tenant without raising for global work."""

    return _current_tenant_id.get()


@contextmanager
def tenant_scope(tenant_id: UUID) -> Generator[UUID, None, None]:
    """Set a tenant for the duration of one request or background operation."""

    token = _current_tenant_id.set(tenant_id)
    try:
        yield tenant_id
    finally:
        _current_tenant_id.reset(token)


async def set_database_tenant(session: AsyncSession, tenant_id: UUID) -> None:
    """Set PostgreSQL's transaction-local tenant GUC for row-level security.

    SQLite (used for fast repository tests) has no equivalent setting, so the
    application predicate remains the protection in that environment.
    """

    bind = session.get_bind()
    if bind.dialect.name != "postgresql":
        return

    await session.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": str(tenant_id)},
    )


async def set_database_user(session: AsyncSession, user_id: UUID) -> None:
    """Set the authenticated user for the login-only membership RLS policy.

    This scope is used only after password verification, before a tenant has
    been selected. It permits reading that user's own membership rows and does
    not permit tenant-owned writes.
    """

    bind = session.get_bind()
    if bind.dialect.name != "postgresql":
        return

    await session.execute(
        text("SELECT set_config('app.user_id', :user_id, true)"),
        {"user_id": str(user_id)},
    )


async def clear_database_tenant(session: AsyncSession) -> None:
    """Clear the transaction-local tenant GUC when a scope exits."""

    bind = session.get_bind()
    if bind.dialect.name != "postgresql":
        return

    await session.execute(text("SELECT set_config('app.tenant_id', '', true)"))


@asynccontextmanager
async def tenant_session_scope(
    session: AsyncSession,
    tenant_id: UUID,
) -> AsyncGenerator[UUID, None]:
    """Bind both Python and PostgreSQL tenant context for one session scope."""

    with tenant_scope(tenant_id):
        await set_database_tenant(session, tenant_id)
        try:
            yield tenant_id
        finally:
            # ``set_config(..., true)`` is transaction-local. Avoid starting a
            # new transaction merely to clear a setting when the caller has
            # already committed or rolled back the transaction in this scope.
            if session.in_transaction():
                await clear_database_tenant(session)


__all__ = [
    "TenantContextError",
    "clear_database_tenant",
    "get_current_tenant_id",
    "maybe_current_tenant_id",
    "set_database_tenant",
    "set_database_user",
    "tenant_scope",
    "tenant_session_scope",
]
