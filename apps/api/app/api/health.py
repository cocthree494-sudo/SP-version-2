from typing import Any

import structlog
from fastapi import APIRouter, Response
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings

# Setup logging here if needed early, but better done in main
logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/health", tags=["health"])

# We create small temporary clients for health check since full DB connection
# lifecycle will be implemented in T-020 (database base).
async_engine = create_async_engine(settings.DATABASE_URL, echo=False)
redis_client = Redis.from_url(settings.REDIS_URL, decode_responses=True)


@router.get("/live", summary="Liveness probe")
async def live() -> dict[str, str]:
    """Returns 200 immediately to indicate the process is running."""
    return {"status": "ok"}


@router.get("/ready", summary="Readiness probe")
async def ready(response: Response) -> dict[str, Any]:
    """Checks if downstream dependencies (Postgres, Redis) are healthy."""
    db_ok = False
    redis_ok = False
    details = {}

    # Check Database
    try:
        async with async_engine.connect() as conn:
            from sqlalchemy import text
            await conn.execute(text("SELECT 1"))
        db_ok = True
        details["database"] = "ok"
    except Exception as e:
        logger.error("database_health_check_failed", error=str(e))
        details["database"] = "unhealthy"

    # Check Redis
    try:
        await redis_client.ping()
        redis_ok = True
        details["redis"] = "ok"
    except Exception as e:
        logger.error("redis_health_check_failed", error=str(e))
        details["redis"] = "unhealthy"

    is_ready = db_ok and redis_ok

    if not is_ready:
        response.status_code = 503

    return {
        "status": "ready" if is_ready else "unhealthy",
        "details": details,
    }
