import logging
import sys

import structlog
from asgi_correlation_id import correlation_id

from app.core.config import settings


def setup_logging() -> None:
    """Configure structured JSON logging for the application."""
    if structlog.is_configured():
        return

    shared_processors: list[structlog.typing.Processor] = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.contextvars.merge_contextvars,
        _add_correlation_id,
    ]

    processors: list[structlog.typing.Processor]
    if settings.is_local:
        # Better console output in development
        formatter = structlog.dev.ConsoleRenderer(colors=True)
        processors = [*shared_processors, formatter]
    else:
        # JSON logs for production (Datadog/GCP/AWS)
        processors = [
            *shared_processors,
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ]

    structlog.configure(
        processors=processors,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Standard library logging configuration
    handler = logging.StreamHandler(sys.stdout)
    if settings.is_local:
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] [%(name)s] %(message)s")
        )
    else:
        handler.setFormatter(logging.Formatter("%(message)s"))

    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO if not settings.is_local else logging.DEBUG)

    # Prevent uvicorn/fastapi from double logging
    for _log in ("uvicorn", "uvicorn.access", "uvicorn.error", "fastapi"):
        logging.getLogger(_log).handlers.clear()
        logging.getLogger(_log).propagate = True


def _add_correlation_id(
    logger: structlog.typing.BindableLogger,
    method_name: str,
    event_dict: structlog.typing.EventDict,
) -> structlog.typing.EventDict:
    """Add request ID to log entries."""
    if request_id := correlation_id.get():
        event_dict["request_id"] = request_id
    return event_dict
