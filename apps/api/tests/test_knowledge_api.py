"""Secure file and manual knowledge-source API behavior."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any, cast

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.api.knowledge import get_ingestion_queue, get_object_storage
from app.db.base import Base
from app.db.session import get_db_session
from app.domains.auth.models import RefreshToken
from app.domains.bots.models import Bot, BotKey
from app.domains.knowledge.models import Document, DocumentChunk, IngestionJob, KnowledgeSource
from app.domains.tenancy.models import Tenant, TenantMembership, User
from app.main import app
from app.providers.storage import LocalObjectStorage
from app.workers.queue import IngestionQueueMessage
from tests.auth_helpers import register_with_otp


class FakeQueue:
    def __init__(self) -> None:
        self.messages: list[IngestionQueueMessage] = []

    async def enqueue(self, message: IngestionQueueMessage, **_kwargs: object) -> bool:
        if message in self.messages:
            return False
        self.messages.append(message)
        return True


@pytest_asyncio.fixture
async def knowledge_api(
    tmp_path: Path,
) -> AsyncGenerator[tuple[AsyncClient, FakeQueue, Path], None]:
    engine: AsyncEngine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
    )
    tables = [
        cast(Table, User.__table__),
        cast(Table, Tenant.__table__),
        cast(Table, TenantMembership.__table__),
        cast(Table, RefreshToken.__table__),
        cast(Table, Bot.__table__),
        cast(Table, BotKey.__table__),
        cast(Table, KnowledgeSource.__table__),
        cast(Table, Document.__table__),
        cast(Table, DocumentChunk.__table__),
        cast(Table, IngestionJob.__table__),
    ]
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all, tables=tables)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    session = factory()
    queue = FakeQueue()
    storage_root = tmp_path / "uploads"

    async def override_session() -> AsyncGenerator[AsyncSession, None]:
        yield session

    app.dependency_overrides[get_db_session] = override_session
    app.dependency_overrides[get_object_storage] = lambda: LocalObjectStorage(storage_root)
    app.dependency_overrides[get_ingestion_queue] = lambda: queue
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, queue, storage_root
    app.dependency_overrides.clear()
    await session.close()
    await engine.dispose()


async def register_and_create_bot(
    client: AsyncClient,
    *,
    email: str,
    slug: str,
) -> tuple[dict[str, str], dict[str, Any]]:
    registered = await register_with_otp(
        client,
        {
            "email": email,
            "password": "correct horse battery staple",
            "organization_name": slug.title(),
            "organization_slug": slug,
        },
    )
    headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
    bot = await client.post("/v1/bots", headers=headers, json={"name": f"{slug} bot"})
    assert bot.status_code == 201
    return headers, cast(dict[str, Any], bot.json())


@pytest.mark.asyncio
async def test_file_upload_validates_persists_lists_and_cleans_up(
    knowledge_api: tuple[AsyncClient, FakeQueue, Path],
) -> None:
    client, queue, storage_root = knowledge_api
    headers, bot = await register_and_create_bot(client, email="owner@example.com", slug="files")
    uploaded = await client.post(
        f"/v1/bots/{bot['id']}/sources/files",
        headers=headers,
        data={"name": "Returns guide"},
        files={"file": ("guide.md", b"# Returns\n\nRefunds take five days.", "text/markdown")},
    )
    assert uploaded.status_code == 201
    source = uploaded.json()
    assert source["type"] == "file"
    assert source["status"] == "pending"
    assert source["details"]["file_kind"] == "md"
    assert source["details"]["checksum_sha256"]
    assert len(queue.messages) == 1
    assert len(list(storage_root.rglob("*.md"))) == 1

    listed = await client.get(f"/v1/bots/{bot['id']}/sources", headers=headers)
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [source["id"]]

    invalid = await client.post(
        f"/v1/bots/{bot['id']}/sources/files",
        headers=headers,
        files={"file": ("fake.pdf", b"not a pdf", "application/pdf")},
    )
    assert invalid.status_code == 422
    assert not list(storage_root.rglob("*.tmp"))

    deleted = await client.delete(f"/v1/sources/{source['id']}", headers=headers)
    assert deleted.status_code == 204
    assert not list(storage_root.rglob("*.md"))


@pytest.mark.asyncio
async def test_manual_source_reembeds_on_change_and_is_tenant_isolated(
    knowledge_api: tuple[AsyncClient, FakeQueue, Path],
) -> None:
    client, queue, _storage_root = knowledge_api
    first_headers, bot = await register_and_create_bot(
        client,
        email="manual@example.com",
        slug="manual",
    )
    created = await client.post(
        f"/v1/bots/{bot['id']}/sources/manual",
        headers=first_headers,
        json={"question": "How do refunds work?", "answer": "They take five days."},
    )
    assert created.status_code == 201
    source = created.json()
    assert source["details"]["question"] == "How do refunds work?"
    assert len(queue.messages) == 1

    updated = await client.patch(
        f"/v1/sources/{source['id']}/manual",
        headers=first_headers,
        json={"answer": "They take three days."},
    )
    assert updated.status_code == 200
    assert updated.json()["details"]["answer"] == "They take three days."
    assert len(queue.messages) == 2

    second_headers, _second_bot = await register_and_create_bot(
        client,
        email="other@example.com",
        slug="other",
    )
    cross_tenant = await client.get(f"/v1/sources/{source['id']}", headers=second_headers)
    assert cross_tenant.status_code == 404
