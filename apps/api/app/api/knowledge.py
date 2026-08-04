"""Authenticated knowledge-source APIs."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import CurrentAuth
from app.api.bots import BotManager
from app.db.session import get_db_session
from app.domains.bots.repositories import BotRepository
from app.domains.knowledge.files import FileSourceService, FileTooLargeError, FileUploadError
from app.domains.knowledge.manual import ManualSourceError, ManualSourceService
from app.domains.knowledge.repositories import KnowledgeSourceRepository
from app.domains.knowledge.schemas import (
    KnowledgeSourceResponse,
    ManualSourceCreateRequest,
    ManualSourceUpdateRequest,
    WebsiteSourceCreateRequest,
    source_response,
)
from app.domains.knowledge.websites import WebsiteSourceError, WebsiteSourceService
from app.providers.storage import ObjectStorage, build_object_storage
from app.workers.queue import IngestionQueue

router = APIRouter(prefix="/v1", tags=["knowledge"])
DbSession = Annotated[AsyncSession, Depends(get_db_session)]


def get_object_storage() -> ObjectStorage:
    return build_object_storage()


def get_ingestion_queue(request: Request) -> IngestionQueue:
    queue = getattr(request.app.state, "ingestion_queue", None)
    if queue is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Ingestion queue is unavailable",
        )
    return queue


StorageDependency = Annotated[ObjectStorage, Depends(get_object_storage)]
QueueDependency = Annotated[IngestionQueue, Depends(get_ingestion_queue)]


@router.post(
    "/bots/{bot_id}/sources/files",
    response_model=KnowledgeSourceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_file_source(
    bot_id: UUID,
    session: DbSession,
    context: BotManager,
    storage: StorageDependency,
    queue: QueueDependency,
    file: Annotated[UploadFile, File()],
    name: Annotated[str | None, Form(max_length=200)] = None,
) -> KnowledgeSourceResponse:
    try:
        source = await FileSourceService(
            session,
            context.tenant.id,
            storage,
            queue,
        ).create(bot_id=bot_id, upload=file, display_name=name)
    except FileTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=str(exc),
        ) from None
    except FileUploadError as exc:
        response_status = (
            status.HTTP_404_NOT_FOUND
            if exc.code == "bot_not_found"
            else status.HTTP_422_UNPROCESSABLE_CONTENT
        )
        raise HTTPException(status_code=response_status, detail=str(exc)) from None
    finally:
        await file.close()
    return source_response(source)


@router.post(
    "/bots/{bot_id}/sources/websites",
    response_model=KnowledgeSourceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_website_source(
    bot_id: UUID,
    payload: WebsiteSourceCreateRequest,
    session: DbSession,
    context: BotManager,
    queue: QueueDependency,
) -> KnowledgeSourceResponse:
    try:
        source = await WebsiteSourceService(session, context.tenant.id, queue).create(
            bot_id=bot_id,
            payload=payload,
        )
    except WebsiteSourceError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from None
    return source_response(source)


@router.post(
    "/bots/{bot_id}/sources/manual",
    response_model=KnowledgeSourceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_manual_source(
    bot_id: UUID,
    payload: ManualSourceCreateRequest,
    session: DbSession,
    context: BotManager,
    queue: QueueDependency,
) -> KnowledgeSourceResponse:
    try:
        source = await ManualSourceService(session, context.tenant.id, queue).create(
            bot_id=bot_id,
            payload=payload,
        )
    except ManualSourceError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from None
    return source_response(source)


@router.patch(
    "/sources/{source_id}/manual",
    response_model=KnowledgeSourceResponse,
)
async def update_manual_source(
    source_id: UUID,
    payload: ManualSourceUpdateRequest,
    session: DbSession,
    context: BotManager,
    queue: QueueDependency,
) -> KnowledgeSourceResponse:
    try:
        source = await ManualSourceService(session, context.tenant.id, queue).update(
            source_id=source_id,
            payload=payload,
        )
    except ManualSourceError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from None
    return source_response(source)


@router.get("/bots/{bot_id}/sources", response_model=list[KnowledgeSourceResponse])
async def list_sources(
    bot_id: UUID,
    session: DbSession,
    context: CurrentAuth,
) -> list[KnowledgeSourceResponse]:
    if await BotRepository(session, context.tenant.id).get(bot_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bot not found")
    sources = await KnowledgeSourceRepository(session, context.tenant.id).list_for_bot(bot_id)
    return [source_response(source) for source in sources]


@router.get("/sources/{source_id}", response_model=KnowledgeSourceResponse)
async def get_source(
    source_id: UUID,
    session: DbSession,
    context: CurrentAuth,
) -> KnowledgeSourceResponse:
    source = await KnowledgeSourceRepository(session, context.tenant.id).get(source_id)
    if source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge source not found",
        )
    return source_response(source)


@router.delete("/sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source(
    source_id: UUID,
    session: DbSession,
    context: BotManager,
    storage: StorageDependency,
    queue: QueueDependency,
) -> Response:
    deleted = await FileSourceService(
        session,
        context.tenant.id,
        storage,
        queue,
    ).delete(source_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge source not found",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["get_ingestion_queue", "get_object_storage", "router"]
