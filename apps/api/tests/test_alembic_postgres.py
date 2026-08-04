"""Live migration round-trip and model/schema parity checks."""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import settings
from app.db.base import Base
from app.db.migrations import include_object
from app.domains.auth import models as _auth_models  # noqa: F401
from app.domains.bots import models as _bot_models  # noqa: F401
from app.domains.chat import models as _chat_models  # noqa: F401
from app.domains.knowledge import models as _knowledge_models  # noqa: F401
from app.domains.tenancy import models as _tenancy_models  # noqa: F401
from app.domains.usage import models as _usage_models  # noqa: F401


def _alembic_command(api_root: Path, revision: str) -> None:
    environment = os.environ.copy()
    environment["DATABASE_URL"] = settings.DATABASE_URL
    result = subprocess.run(  # noqa: S603 - command and revision are fixed by this test
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", revision],
        cwd=api_root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"alembic {revision} failed\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def _migration_diff(connection: Connection) -> list[Any]:
    context = MigrationContext.configure(
        connection,
        opts={
            "compare_type": True,
            "compare_server_default": True,
            "include_object": include_object,
        },
    )
    return compare_metadata(context, Base.metadata)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_postgres_migrations_round_trip_and_match_models(
    postgres_engine: AsyncEngine,
    admin_postgres_engine: AsyncEngine,
) -> None:
    del postgres_engine
    api_root = Path(__file__).resolve().parents[1]
    await asyncio.to_thread(_alembic_command, api_root, "upgrade head")
    await asyncio.to_thread(_alembic_command, api_root, "downgrade base")
    await asyncio.to_thread(_alembic_command, api_root, "upgrade head")

    async with admin_postgres_engine.connect() as connection:
        differences = await connection.run_sync(_migration_diff)
    assert differences == [], f"Alembic autogenerate found schema drift: {differences!r}"
