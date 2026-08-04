"""Tenant-addressed object storage interface and atomic local adapter."""

from __future__ import annotations

import hashlib
import os
from collections.abc import AsyncIterable, AsyncIterator
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Protocol, runtime_checkable
from uuid import UUID, uuid4

import anyio
from anyio import to_thread

from app.core.config import settings


class InvalidStorageKeyError(ValueError):
    """Raised when a logical object key could escape its tenant prefix."""


@dataclass(frozen=True, slots=True)
class StoredObject:
    """Provider-neutral metadata returned after an object is persisted."""

    key: str
    size_bytes: int
    checksum_sha256: str


@runtime_checkable
class ObjectStorage(Protocol):
    """Streaming interface implementable by local or S3-compatible storage.

    Production adapters must map every object to ``<tenant_id>/<key>`` and
    preserve the same exact tenant boundary as the local implementation.
    """

    async def put_stream(
        self,
        tenant_id: UUID,
        key: str,
        chunks: AsyncIterable[bytes],
    ) -> StoredObject: ...

    def read_stream(
        self,
        tenant_id: UUID,
        key: str,
        *,
        chunk_size: int = 64 * 1024,
    ) -> AsyncIterator[bytes]: ...

    async def delete(self, tenant_id: UUID, key: str) -> bool: ...

    async def exists(self, tenant_id: UUID, key: str) -> bool: ...


@runtime_checkable
class S3CompatibleObjectStorage(ObjectStorage, Protocol):
    """Marker protocol for production S3-compatible implementations.

    An adapter may use AWS S3, Cloudflare R2, MinIO, or another compatible
    service, but it must retain tenant-prefixed keys and the streaming contract.
    """


def normalize_storage_key(key: str) -> str:
    """Validate a portable relative POSIX key without traversal components."""

    raw = key.strip()
    if not raw or "\x00" in raw or "\\" in raw:
        raise InvalidStorageKeyError("Storage key must be a non-empty POSIX path")
    path = PurePosixPath(raw)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise InvalidStorageKeyError("Storage key must stay within its tenant prefix")
    normalized = path.as_posix()
    if normalized != raw:
        raise InvalidStorageKeyError("Storage key must use canonical POSIX separators")
    return normalized


class LocalObjectStorage:
    """Atomic development storage rooted under UUID tenant directories."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def _object_path(self, tenant_id: UUID, key: str) -> tuple[str, Path]:
        normalized = normalize_storage_key(key)
        tenant_root = (self.root / str(tenant_id)).resolve()
        object_path = (tenant_root / Path(*PurePosixPath(normalized).parts)).resolve()
        try:
            object_path.relative_to(tenant_root)
        except ValueError as exc:
            raise InvalidStorageKeyError("Storage key escaped its tenant prefix") from exc
        return normalized, object_path

    async def put_stream(
        self,
        tenant_id: UUID,
        key: str,
        chunks: AsyncIterable[bytes],
    ) -> StoredObject:
        normalized, object_path = self._object_path(tenant_id, key)
        await to_thread.run_sync(lambda: object_path.parent.mkdir(parents=True, exist_ok=True))
        temporary_path = object_path.with_name(f".{object_path.name}.{uuid4().hex}.tmp")
        checksum = hashlib.sha256()
        size_bytes = 0
        try:
            async with await anyio.open_file(temporary_path, "wb") as output:
                async for chunk in chunks:
                    if not isinstance(chunk, bytes):
                        raise TypeError("Storage chunks must be bytes")
                    if not chunk:
                        continue
                    await output.write(chunk)
                    checksum.update(chunk)
                    size_bytes += len(chunk)
            await to_thread.run_sync(os.replace, temporary_path, object_path)
        except BaseException:
            await to_thread.run_sync(lambda: temporary_path.unlink(missing_ok=True))
            raise

        return StoredObject(
            key=normalized,
            size_bytes=size_bytes,
            checksum_sha256=checksum.hexdigest(),
        )

    async def read_stream(
        self,
        tenant_id: UUID,
        key: str,
        *,
        chunk_size: int = 64 * 1024,
    ) -> AsyncIterator[bytes]:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        _normalized, object_path = self._object_path(tenant_id, key)
        async with await anyio.open_file(object_path, "rb") as source:
            while chunk := await source.read(chunk_size):
                yield chunk

    async def delete(self, tenant_id: UUID, key: str) -> bool:
        _normalized, object_path = self._object_path(tenant_id, key)

        def _delete() -> bool:
            try:
                object_path.unlink()
            except FileNotFoundError:
                return False
            return True

        return await to_thread.run_sync(_delete)

    async def exists(self, tenant_id: UUID, key: str) -> bool:
        _normalized, object_path = self._object_path(tenant_id, key)
        return await to_thread.run_sync(object_path.is_file)


def build_object_storage(root: Path | None = None) -> ObjectStorage:
    """Build the configured development adapter behind the provider interface."""

    return LocalObjectStorage(settings.LOCAL_STORAGE_ROOT if root is None else root)


__all__ = [
    "InvalidStorageKeyError",
    "LocalObjectStorage",
    "ObjectStorage",
    "S3CompatibleObjectStorage",
    "StoredObject",
    "build_object_storage",
    "normalize_storage_key",
]
