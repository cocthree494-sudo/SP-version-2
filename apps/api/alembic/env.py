"""Alembic environment configured for the async application engine."""

from __future__ import annotations

import asyncio
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import Connection
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy.pool import NullPool

# Running ``alembic`` from either the API directory or the repository root
# should resolve the application package identically.
api_root = Path(__file__).resolve().parents[1]
if str(api_root) not in sys.path:
    sys.path.insert(0, str(api_root))

from app.core.config import settings  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.domains.tenancy import models as tenancy_models  # noqa: E402,F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _configure_url() -> str:
    """Use typed application settings while keeping Alembic's config useful."""

    # Validate that the configured value is a SQLAlchemy URL before handing it
    # to Alembic. This gives a clear startup error for malformed environments.
    return make_url(settings.DATABASE_URL).render_as_string(hide_password=False)


def run_migrations_offline() -> None:
    """Run migrations without opening a database connection."""

    context.configure(
        url=_configure_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Configure Alembic for one synchronous connection callback."""

    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create an async engine and run Alembic's sync migration callback."""

    connectable = async_engine_from_config(
        {
            "sqlalchemy.url": _configure_url(),
        },
        prefix="sqlalchemy.",
        poolclass=NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations() -> None:
    """Dispatch to offline or online migration execution."""

    if context.is_offline_mode():
        run_migrations_offline()
    else:
        asyncio.run(run_async_migrations())


run_migrations()
