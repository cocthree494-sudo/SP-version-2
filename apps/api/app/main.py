from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from asgi_correlation_id import CorrelationIdMiddleware
from fastapi import FastAPI

from app.api import auth, bots, health, usage
from app.core.config import settings
from app.core.logger import setup_logging
from app.db.session import dispose_engine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Setup structured logging on startup
    setup_logging()
    try:
        yield
    finally:
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
app.include_router(usage.router)


@app.get("/", include_in_schema=False)
async def service_info() -> dict[str, str]:
    return {
        "service": "support-agent-api",
        "status": "scaffold-ready",
        "env": settings.APP_ENV,
    }
