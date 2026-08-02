"""Tests for the async SQLAlchemy session factory."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session_factory


@pytest.mark.asyncio
async def test_session_factory_creates_async_sessions_without_eager_connection() -> None:
    async with async_session_factory() as session:
        assert isinstance(session, AsyncSession)
        assert session.sync_session.expire_on_commit is False
