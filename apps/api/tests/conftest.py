"""Shared fixtures for real PostgreSQL/pgvector security integration tests."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.config import settings

TENANT_TABLES = (
    "tenant_memberships",
    "refresh_tokens",
    "bots",
    "bot_keys",
    "usage_events",
    "knowledge_sources",
    "documents",
    "ingestion_jobs",
    "document_chunks",
    "conversations",
    "messages",
    "provider_credentials",
    "provider_policies",
    "channel_installations",
    "voice_agent_installations",
    "voice_webhook_events",
)


def _integration_database_url() -> str:
    return settings.TEST_DATABASE_URL or settings.DATABASE_URL


def _is_ci() -> bool:
    return os.environ.get("CI", "").casefold() in {"1", "true", "yes"}


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def postgres_engine() -> AsyncIterator[AsyncEngine]:
    """Connect as the deliberately weak role that must be subject to RLS."""

    engine = create_async_engine(_integration_database_url(), poolclass=NullPool)
    try:
        try:
            async with engine.connect() as connection:
                row = (
                    await connection.execute(
                        text(
                            "SELECT current_user, rolsuper, rolbypassrls "
                            "FROM pg_roles WHERE rolname = current_user"
                        )
                    )
                ).one()
                role_name, is_super, bypasses_rls = row
                assert not is_super, (
                    "RLS tests are meaningless when connected as a superuser"
                )
                assert not bypasses_rls, (
                    "RLS tests are meaningless with BYPASSRLS"
                )
                owned_tables = await connection.scalar(
                    text(
                        "SELECT count(*) FROM pg_tables "
                        "WHERE schemaname = 'public' AND tableowner = current_user"
                    )
                )
                assert owned_tables == 0, (
                    f"RLS test role {role_name} must not own application tables"
                )
        except (OSError, SQLAlchemyError) as exc:
            message = (
                "PostgreSQL integration database is unavailable. Start the pgvector "
                "service, apply migrations, and configure TEST_DATABASE_URL."
            )
            if _is_ci():
                pytest.fail(f"{message} CI may never skip this security gate: {exc}")
            pytest.skip(f"{message} ({exc})")
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def admin_postgres_engine(
    postgres_engine: AsyncEngine,
) -> AsyncIterator[AsyncEngine]:
    """Provide the migration-owner connection only for setup and schema checks."""

    del postgres_engine
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def pg_session(postgres_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Yield a restricted-role session and roll back all test-local writes."""

    factory = async_sessionmaker(postgres_engine, expire_on_commit=False)
    async with factory() as session:
        try:
            yield session
        finally:
            await session.rollback()
