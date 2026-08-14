"""Helpers that complete the same two-step authentication contract as production."""

from __future__ import annotations

from typing import Any, cast

from httpx import AsyncClient, Response

from app.domains.auth.email import InMemoryAuthEmailSender
from app.main import app


def latest_otp(email: str) -> str:
    sender = cast(InMemoryAuthEmailSender, app.state.auth_email_sender)
    return sender.latest_code_for(email)


async def verify_latest_otp(
    client: AsyncClient,
    challenge_response: Response,
    *,
    email: str,
) -> Response:
    challenge_id = challenge_response.json()["challenge_id"]
    return await client.post(
        "/v1/auth/otp/verify",
        json={"challenge_id": challenge_id, "code": latest_otp(email)},
    )


async def register_with_otp(
    client: AsyncClient,
    payload: dict[str, Any],
) -> Response:
    started = await client.post("/v1/auth/register", json=payload)
    assert started.status_code == 202, started.text
    verified = await verify_latest_otp(
        client,
        started,
        email=str(payload["email"]),
    )
    assert verified.status_code == 200, verified.text
    return verified


async def login_with_otp(
    client: AsyncClient,
    payload: dict[str, Any],
) -> Response:
    started = await client.post("/v1/auth/login", json=payload)
    assert started.status_code == 200, started.text
    verified = await verify_latest_otp(
        client,
        started,
        email=str(payload["email"]),
    )
    assert verified.status_code == 200, verified.text
    return verified


__all__ = ["latest_otp", "login_with_otp", "register_with_otp", "verify_latest_otp"]
