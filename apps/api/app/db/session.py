"""Async SQLAlchemy engine and request-scoped session dependency."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
)

async_session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

# A conventional alias makes the factory easy to discover in repositories and
# keeps future dependency-injection code independent of its implementation.
SessionLocal = async_session_factory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield one isolated async session for a request or background job.

    Transactions are deliberately not committed here. Domain services own
    their commit boundaries; an exception still rolls back any pending work so
    a failed request cannot leak a transaction into the connection pool.
    """

    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


# Keep the dependency name explicit for FastAPI route declarations.
get_db_session = get_session


async def dispose_engine() -> None:
    """Close pooled database connections during application shutdown."""

    await engine.dispose()


__all__ = [
    "SessionLocal",
    "async_session_factory",
    "dispose_engine",
    "engine",
    "get_db_session",
    "get_session",
]
