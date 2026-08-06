"""Set the restricted production runtime-role password after migrations."""

from __future__ import annotations

import asyncio
import os

from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import create_async_engine

EXPECTED_ROLE = "support_agent_app"


async def configure_runtime_role() -> None:
    owner_database_url = os.environ.get("DATABASE_URL")
    app_database_url = os.environ.get("APP_DATABASE_URL")
    if not owner_database_url or not app_database_url:
        raise RuntimeError("DATABASE_URL and APP_DATABASE_URL are required")
    app_url = make_url(app_database_url)
    if app_url.username != EXPECTED_ROLE or not app_url.password:
        raise RuntimeError(
            f"APP_DATABASE_URL must authenticate as {EXPECTED_ROLE} with a password"
        )

    engine = create_async_engine(owner_database_url)
    try:
        async with engine.begin() as connection:
            role = await connection.scalar(
                text("SELECT quote_ident(:role)"),
                {"role": EXPECTED_ROLE},
            )
            password = await connection.scalar(
                text("SELECT quote_literal(:password)"),
                {"password": app_url.password},
            )
            if not isinstance(role, str) or not isinstance(password, str):
                raise RuntimeError("PostgreSQL did not safely quote runtime credentials")
            await connection.execute(text(f"ALTER ROLE {role} PASSWORD {password}"))
            can_login, is_super, bypasses_rls = (
                await connection.execute(
                    text(
                        "SELECT rolcanlogin, rolsuper, rolbypassrls "
                        "FROM pg_roles WHERE rolname = :role"
                    ),
                    {"role": EXPECTED_ROLE},
                )
            ).one()
            if not can_login or is_super or bypasses_rls:
                raise RuntimeError("Runtime role has unsafe PostgreSQL attributes")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(configure_runtime_role())
