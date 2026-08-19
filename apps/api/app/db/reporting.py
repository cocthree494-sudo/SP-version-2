"""Dedicated least-privilege connection for platform reporting views."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

reporting_engine: AsyncEngine = create_async_engine(
    settings.admin_reporting_database_url,
    echo=False,
    pool_pre_ping=True,
)
reporting_session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=reporting_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_reporting_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield a read-only reporting session and never commit through it."""

    async with reporting_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def dispose_reporting_engine() -> None:
    await reporting_engine.dispose()


__all__ = ["dispose_reporting_engine", "get_reporting_session", "reporting_engine"]
