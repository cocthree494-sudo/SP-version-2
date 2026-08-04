"""Provision the restricted role password used by PostgreSQL integration tests.

The migration owns role creation and grants. This CI/local bootstrap command only
sets the environment-specific password from ``TEST_DATABASE_URL`` and verifies
that the target role cannot bypass row-level security.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings

EXPECTED_ROLE = "support_agent_app"


async def configure_test_role() -> None:
    test_database_url = settings.TEST_DATABASE_URL
    if not test_database_url:
        raise RuntimeError("DATABASE_URL and TEST_DATABASE_URL are both required")

    test_url = make_url(test_database_url)
    if test_url.username != EXPECTED_ROLE or not test_url.password:
        raise RuntimeError(
            f"TEST_DATABASE_URL must authenticate as {EXPECTED_ROLE} with a password"
        )

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with engine.begin() as connection:
            role = await connection.scalar(
                text("SELECT quote_ident(:role)"),
                {"role": EXPECTED_ROLE},
            )
            password = await connection.scalar(
                text("SELECT quote_literal(:password)"),
                {"password": test_url.password},
            )
            if not isinstance(role, str) or not isinstance(password, str):
                raise RuntimeError("PostgreSQL did not return safely quoted role credentials")
            await connection.execute(text(f"ALTER ROLE {role} PASSWORD {password}"))
            attributes = (
                await connection.execute(
                    text(
                        "SELECT rolcanlogin, rolsuper, rolbypassrls "
                        "FROM pg_roles WHERE rolname = :role"
                    ),
                    {"role": EXPECTED_ROLE},
                )
            ).one()
            can_login, is_super, bypasses_rls = attributes
            if not can_login or is_super or bypasses_rls:
                raise RuntimeError("Restricted integration-test role has unsafe attributes")
    finally:
        await engine.dispose()


def main() -> int:
    asyncio.run(configure_test_role())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
