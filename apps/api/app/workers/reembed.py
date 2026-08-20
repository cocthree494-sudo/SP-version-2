"""Re-embed stored document chunks with the currently configured provider.

Chunk text is authoritative and retained in ``document_chunks.content``, so
changing embedding provider, model, or dimensions never requires re-uploading a
file, re-entering a Q&A, or re-crawling a website. This is a standalone command:
embedding never runs inside API request workers.

Usage from the API image:

    python -m app.workers.reembed --dry-run
    python -m app.workers.reembed
    python -m app.workers.reembed --tenant <uuid> --force
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from uuid import UUID

import structlog
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.tenancy import tenant_session_scope
from app.db.models import register_model_mappings
from app.db.session import async_session_factory, dispose_engine
from app.domains.knowledge.models import DocumentChunk
from app.domains.tenancy.models import Tenant
from app.providers.embeddings import EmbeddingProvider, EmbeddingProviderError
from app.providers.factory import build_embedding_provider

logger = structlog.get_logger(__name__)


class ReembedError(RuntimeError):
    """Safe operator-facing failure that never carries provider credentials."""


@dataclass(slots=True)
class ReembedReport:
    tenant_id: UUID
    stale_chunks: int = 0
    reembedded_chunks: int = 0
    input_tokens: int = 0


def _stale_predicate(provider: EmbeddingProvider) -> object:
    """Chunks whose stored vector does not match the configured provider."""

    return or_(
        DocumentChunk.embedding_provider != provider.provider_id,
        DocumentChunk.embedding_model != provider.model_id,
        func.vector_dims(DocumentChunk.embedding) != provider.dimensions,
    )


async def _tenant_ids(session: AsyncSession) -> list[UUID]:
    result = await session.scalars(select(Tenant.id).order_by(Tenant.created_at))
    return list(result.all())


async def _count_stale(
    session: AsyncSession,
    tenant_id: UUID,
    provider: EmbeddingProvider,
    *,
    force: bool,
) -> int:
    statement = select(func.count()).select_from(DocumentChunk).where(
        DocumentChunk.tenant_id == tenant_id
    )
    if not force:
        statement = statement.where(_stale_predicate(provider))
    return int(await session.scalar(statement) or 0)


async def _next_batch(
    session: AsyncSession,
    tenant_id: UUID,
    provider: EmbeddingProvider,
    *,
    force: bool,
    after: UUID | None,
) -> list[tuple[UUID, str]]:
    statement = select(DocumentChunk.id, DocumentChunk.content).where(
        DocumentChunk.tenant_id == tenant_id
    )
    if not force:
        statement = statement.where(_stale_predicate(provider))
    if after is not None:
        statement = statement.where(DocumentChunk.id > after)
    statement = statement.order_by(DocumentChunk.id).limit(settings.EMBEDDING_BATCH_SIZE)
    result = await session.execute(statement)
    return [(row[0], row[1]) for row in result.all()]


async def reembed_tenant(
    tenant_id: UUID,
    provider: EmbeddingProvider,
    *,
    force: bool = False,
    dry_run: bool = False,
) -> ReembedReport:
    """Re-embed one tenant's stale chunks in place, committing batch by batch."""

    report = ReembedReport(tenant_id=tenant_id)
    async with async_session_factory() as session, tenant_session_scope(session, tenant_id):
        report.stale_chunks = await _count_stale(session, tenant_id, provider, force=force)
    if dry_run or report.stale_chunks == 0:
        return report

    after: UUID | None = None
    while True:
        # A fresh scope per batch keeps the transaction-local tenant GUC valid
        # after each commit, so a long run stays resumable and fail-closed.
        async with async_session_factory() as session, tenant_session_scope(session, tenant_id):
            batch = await _next_batch(
                session, tenant_id, provider, force=force, after=after
            )
            if not batch:
                return report
            try:
                response = await provider.embed([content for _chunk_id, content in batch])
            except EmbeddingProviderError as exc:
                raise ReembedError(
                    f"Embedding provider rejected a batch of {len(batch)} chunks: {exc}"
                ) from exc
            if len(response.embeddings) != len(batch):
                raise ReembedError("Embedding provider returned an invalid item count")
            for (chunk_id, _content), embedding in zip(
                batch, response.embeddings, strict=True
            ):
                if len(embedding) != provider.dimensions:
                    raise ReembedError(
                        "Embedding provider returned an unexpected dimension; "
                        "check EMBEDDING_DIMENSIONS against the model"
                    )
                await session.execute(
                    update(DocumentChunk)
                    .where(
                        DocumentChunk.tenant_id == tenant_id,
                        DocumentChunk.id == chunk_id,
                    )
                    .values(
                        embedding=embedding,
                        embedding_provider=provider.provider_id,
                        embedding_model=provider.model_id,
                    )
                )
            await session.commit()
            report.reembedded_chunks += len(batch)
            report.input_tokens += response.usage.input_tokens
            after = batch[-1][0]
        logger.info(
            "reembed.batch",
            tenant_id=str(tenant_id),
            reembedded=report.reembedded_chunks,
            stale=report.stale_chunks,
        )


async def run(
    *,
    tenant_id: UUID | None = None,
    force: bool = False,
    dry_run: bool = False,
) -> list[ReembedReport]:
    register_model_mappings()
    provider = build_embedding_provider()
    reports: list[ReembedReport] = []
    try:
        if tenant_id is None:
            async with async_session_factory() as session:
                tenants = await _tenant_ids(session)
        else:
            tenants = [tenant_id]
        for target in tenants:
            reports.append(
                await reembed_tenant(target, provider, force=force, dry_run=dry_run)
            )
    finally:
        close = getattr(provider, "aclose", None)
        if close is not None:
            await close()
        await dispose_engine()
    return reports


def _print_reports(reports: list[ReembedReport], *, dry_run: bool) -> None:
    verb = "would re-embed" if dry_run else "re-embedded"
    total_stale = sum(report.stale_chunks for report in reports)
    total_done = sum(report.reembedded_chunks for report in reports)
    total_tokens = sum(report.input_tokens for report in reports)
    lines = [
        f"tenant {report.tenant_id}: {verb} {report.stale_chunks} chunks "
        f"({report.input_tokens} input tokens)"
        for report in reports
        if report.stale_chunks
    ]
    lines.append(
        f"total: {total_stale} stale chunks, {total_done} {verb}, "
        f"{total_tokens} input tokens across {len(reports)} tenants"
    )
    sys.stdout.write("\n".join(lines) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Re-embed document chunks with the configured embedding provider"
    )
    parser.add_argument("--tenant", help="Limit the run to one tenant UUID")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-embed every chunk, not only those from a different provider/model",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report how many chunks are stale without calling the provider",
    )
    args = parser.parse_args()
    tenant_id = UUID(args.tenant) if args.tenant else None

    sys.stdout.write(
        f"embedding provider: mode={settings.embedding_provider_mode} "
        f"provider={settings.EMBEDDING_PROVIDER_ID} model={settings.EMBEDDING_MODEL_ID} "
        f"dimensions={settings.EMBEDDING_DIMENSIONS}\n"
    )
    try:
        reports = asyncio.run(run(tenant_id=tenant_id, force=args.force, dry_run=args.dry_run))
    except ReembedError as exc:
        sys.stderr.write(f"failed: {exc}\n")
        return 1
    _print_reports(reports, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["ReembedError", "ReembedReport", "main", "reembed_tenant", "run"]
