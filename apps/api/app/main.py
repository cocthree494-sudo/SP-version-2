from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from asgi_correlation_id import CorrelationIdMiddleware
from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from redis.asyncio import Redis

from app.api import auth, bots, channels, health, knowledge, playground, providers, usage, widget
from app.core.config import settings
from app.core.logger import setup_logging
from app.db.session import dispose_engine
from app.domains.auth.oauth import RedisOAuthStateStore
from app.domains.chat.rate_limit import RedisRateLimiter
from app.providers.router import RedisCircuitStore
from app.workers.queue import create_ingestion_queue


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Setup structured logging on startup
    setup_logging()
    app.state.ingestion_queue = await create_ingestion_queue()
    app.state.widget_redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    app.state.oauth_state_store = RedisOAuthStateStore(app.state.widget_redis)
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


@app.exception_handler(RequestValidationError)
async def secret_safe_validation_error(
    _request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Keep write-only credentials out of otherwise useful validation errors."""

    secret_fields = {"api_key", "password", "refresh_token"}
    errors: list[dict[str, object]] = []
    for error in exc.errors():
        sanitized = dict(error)
        location = sanitized.get("loc", ())
        if isinstance(location, (list, tuple)) and any(
            item in secret_fields for item in location
        ):
            sanitized["input"] = "**********"
            sanitized.pop("ctx", None)
        errors.append(sanitized)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content=jsonable_encoder({"detail": errors}),
    )

# Include routers
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(bots.router)
app.include_router(channels.router)
app.include_router(knowledge.router)
app.include_router(usage.router)
app.include_router(providers.router)
app.include_router(playground.router)
app.include_router(widget.router)


@app.get("/", include_in_schema=False)
async def service_info() -> dict[str, str]:
    return {
        "service": "support-agent-api",
        "status": "scaffold-ready",
        "env": settings.APP_ENV,
    }
