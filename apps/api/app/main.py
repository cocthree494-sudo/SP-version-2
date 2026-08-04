from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from asgi_correlation_id import CorrelationIdMiddleware
from fastapi import FastAPI
from redis.asyncio import Redis

from app.api import auth, bots, health, knowledge, usage, widget
from app.core.config import settings
from app.core.logger import setup_logging
from app.db.session import dispose_engine
from app.domains.chat.rate_limit import RedisRateLimiter
from app.providers.router import RedisCircuitStore
from app.workers.queue import create_ingestion_queue


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Setup structured logging on startup
    setup_logging()
    app.state.ingestion_queue = await create_ingestion_queue()
    app.state.widget_redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    app.state.widget_rate_limiter = RedisRateLimiter(app.state.widget_redis)
    app.state.model_circuit_store = RedisCircuitStore(app.state.widget_redis)
    try:
        yield
    finally:
        await app.state.ingestion_queue.redis.aclose()
        await app.state.widget_redis.aclose()
        await dispose_engine()
        await health.redis_client.aclose()


app = FastAPI(
    title="Support Agent API",
    version="0.1.0",
    docs_url="/docs",
    redoc_url=None,
    lifespan=lifespan,
)

# Add correlation ID middleware for request tracing
app.add_middleware(CorrelationIdMiddleware)

# Include routers
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(bots.router)
app.include_router(knowledge.router)
app.include_router(usage.router)
app.include_router(widget.router)


@app.get("/", include_in_schema=False)
async def service_info() -> dict[str, str]:
    return {
        "service": "support-agent-api",
        "status": "scaffold-ready",
        "env": settings.APP_ENV,
    }
