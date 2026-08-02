"""Cross-tenant isolation tests for tenancy repositories and context."""

from collections.abc import AsyncGenerator
from typing import cast

import pytest
import pytest_asyncio
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.core.tenancy import (
    TenantContextError,
    maybe_current_tenant_id,
    tenant_scope,
    tenant_session_scope,
)
from app.db.base import Base
from app.domains.tenancy.enums import MembershipRole
from app.domains.tenancy.models import Tenant, TenantMembership, User
from app.domains.tenancy.repositories import (
    MembershipRepository,
    TenantRepository,
    UserRepository,
)

TEST_HASH = "test-password-hash"


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    engine: AsyncEngine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
    )
    tables = [
        cast(Table, User.__table__),
        cast(Table, Tenant.__table__),
        cast(Table, TenantMembership.__table__),
    ]
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all, tables=tables)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_membership_queries_cannot_cross_tenant(
    db_session: AsyncSession,
) -> None:
    tenants = TenantRepository(db_session)
    users = UserRepository(db_session)
    tenant_a = await tenants.create(name="Alpha", slug="alpha")
    tenant_b = await tenants.create(name="Beta", slug="beta")
    user_a = await users.create(email="a@example.com", password_hash=TEST_HASH)
    user_b = await users.create(email="b@example.com", password_hash=TEST_HASH)

    membership_a = await MembershipRepository(db_session, tenant_a.id).create(
        user_id=user_a.id,
        role=MembershipRole.OWNER,
    )
    membership_b = await MembershipRepository(db_session, tenant_b.id).create(
        user_id=user_b.id,
        role=MembershipRole.OWNER,
    )
    await db_session.commit()

    tenant_a_repo = MembershipRepository(db_session, tenant_a.id)
    assert await tenant_a_repo.get_by_id(membership_a.id) is not None
    assert await tenant_a_repo.get_by_id(membership_b.id) is None
    assert await tenant_a_repo.get_for_user(user_b.id) is None
    assert [item.id for item in await tenant_a_repo.list_for_tenant()] == [membership_a.id]
    assert await tenant_a_repo.delete(membership_b.id) is False


@pytest.mark.asyncio
async def test_missing_tenant_context_fails_closed(db_session: AsyncSession) -> None:
    repository = MembershipRepository(db_session)

    with pytest.raises(TenantContextError):
        await repository.list_for_tenant()


@pytest.mark.asyncio
async def test_context_var_scopes_repository_to_selected_tenant(
    db_session: AsyncSession,
) -> None:
    tenants = TenantRepository(db_session)
    users = UserRepository(db_session)
    tenant_a = await tenants.create(name="Alpha", slug="alpha-context")
    tenant_b = await tenants.create(name="Beta", slug="beta-context")
    user = await users.create(
        email="context@example.com",
        password_hash=TEST_HASH,
    )
    await MembershipRepository(db_session, tenant_a.id).create(user_id=user.id)
    await MembershipRepository(db_session, tenant_b.id).create(user_id=user.id)
    await db_session.commit()

    with tenant_scope(tenant_a.id):
        memberships = await MembershipRepository(db_session).list_for_tenant()
        assert len(memberships) == 1
        assert memberships[0].tenant_id == tenant_a.id

    with tenant_scope(tenant_b.id):
        memberships = await MembershipRepository(db_session).list_for_tenant()
        assert len(memberships) == 1
        assert memberships[0].tenant_id == tenant_b.id


@pytest.mark.asyncio
async def test_explicit_repository_cannot_override_active_context(
    db_session: AsyncSession,
) -> None:
    tenants = TenantRepository(db_session)
    tenant_a = await tenants.create(name="Alpha", slug="alpha-conflict")
    tenant_b = await tenants.create(name="Beta", slug="beta-conflict")

    with tenant_scope(tenant_a.id):
        repository = MembershipRepository(db_session, tenant_b.id)
        with pytest.raises(TenantContextError):
            await repository.list_for_tenant()


@pytest.mark.asyncio
async def test_tenant_session_scope_restores_context_after_commit(
    db_session: AsyncSession,
) -> None:
    tenants = TenantRepository(db_session)
    tenant = await tenants.create(name="Scoped", slug="scoped-tenant")

    assert maybe_current_tenant_id() is None
    async with tenant_session_scope(db_session, tenant.id):
        assert maybe_current_tenant_id() == tenant.id
        await db_session.commit()
    assert maybe_current_tenant_id() is None
