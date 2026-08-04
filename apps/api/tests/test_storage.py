"""Tenant-safe local object storage contract tests."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from uuid import uuid4

import pytest

from app.providers.storage import InvalidStorageKeyError, LocalObjectStorage


async def chunks(*values: bytes) -> AsyncIterator[bytes]:
    for value in values:
        yield value


async def collect(stream: AsyncIterator[bytes]) -> bytes:
    return b"".join([part async for part in stream])


@pytest.mark.asyncio
async def test_local_storage_is_atomic_and_tenant_namespaced(tmp_path: Path) -> None:
    storage = LocalObjectStorage(tmp_path)
    tenant_a = uuid4()
    tenant_b = uuid4()

    first = await storage.put_stream(tenant_a, "sources/source-a/input.txt", chunks(b"hel", b"lo"))
    second = await storage.put_stream(tenant_b, "sources/source-a/input.txt", chunks(b"other"))

    assert first.size_bytes == 5
    assert first.checksum_sha256 == (
        "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
    )
    assert second.size_bytes == 5
    assert await collect(storage.read_stream(tenant_a, first.key, chunk_size=2)) == b"hello"
    assert await collect(storage.read_stream(tenant_b, second.key)) == b"other"
    assert await storage.exists(tenant_a, first.key) is True
    assert await storage.delete(tenant_a, first.key) is True
    assert await storage.delete(tenant_a, first.key) is False
    assert await storage.exists(tenant_b, second.key) is True


@pytest.mark.asyncio
async def test_local_storage_rejects_traversal_and_removes_partial_files(tmp_path: Path) -> None:
    storage = LocalObjectStorage(tmp_path)
    tenant_id = uuid4()

    for invalid_key in ("", "../secret", "/absolute", "folder\\file", "folder//file"):
        with pytest.raises(InvalidStorageKeyError):
            await storage.exists(tenant_id, invalid_key)

    async def broken_chunks() -> AsyncIterator[bytes]:
        yield b"partial"
        raise RuntimeError("fixture failure")

    with pytest.raises(RuntimeError, match="fixture failure"):
        await storage.put_stream(tenant_id, "sources/failure/input.txt", broken_chunks())

    assert await storage.exists(tenant_id, "sources/failure/input.txt") is False
    assert list(tmp_path.rglob("*.tmp")) == []
