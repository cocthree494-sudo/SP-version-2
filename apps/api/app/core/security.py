"""Password and token primitives for first-party dashboard authentication."""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Any
from uuid import UUID, uuid4

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import settings

_password_hasher = PasswordHasher()


class AccessTokenError(ValueError):
    """Raised when an access token is invalid, expired, or has wrong claims."""


@dataclass(frozen=True, slots=True)
class AccessTokenClaims:
    """Validated claims the application is allowed to trust."""

    user_id: UUID
    tenant_id: UUID
    token_id: UUID
    issued_at: datetime
    otp_verified: bool


def hash_password(password: str) -> str:
    """Hash a password with Argon2id and a fresh random salt."""

    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password without leaking malformed-hash implementation errors."""

    try:
        return _password_hasher.verify(password_hash, password)
    except (InvalidHashError, VerificationError, VerifyMismatchError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    """Return whether a valid stored hash uses outdated Argon2 parameters."""

    try:
        return _password_hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return False


@lru_cache(maxsize=1)
def dummy_password_hash() -> str:
    """Create one process-local hash for constant-work unknown-user logins."""

    return hash_password(secrets.token_urlsafe(32))


def create_access_token(user_id: UUID, tenant_id: UUID) -> tuple[str, int]:
    """Create a tenant-bound, short-lived signed access token."""

    now = datetime.now(UTC)
    ttl_seconds = settings.AUTH_ACCESS_TOKEN_TTL_SECONDS
    payload = {
        "sub": str(user_id),
        "tenant_id": str(tenant_id),
        "jti": str(uuid4()),
        "type": "access",
        "otp_verified": True,
        "iat": now,
        "exp": now + timedelta(seconds=ttl_seconds),
        "iss": settings.AUTH_JWT_ISSUER,
        "aud": settings.AUTH_JWT_AUDIENCE,
    }
    encoded = jwt.encode(
        payload,
        settings.auth_jwt_secret,
        algorithm=settings.AUTH_JWT_ALGORITHM,
    )
    return encoded, ttl_seconds


def decode_access_token(token: str) -> AccessTokenClaims:
    """Verify an access JWT and return only parsed, expected claims."""

    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.auth_jwt_secret,
            algorithms=[settings.AUTH_JWT_ALGORITHM],
            audience=settings.AUTH_JWT_AUDIENCE,
            issuer=settings.AUTH_JWT_ISSUER,
            options={
                "require": [
                    "sub",
                    "tenant_id",
                    "jti",
                    "type",
                    "otp_verified",
                    "iat",
                    "exp",
                ]
            },
        )
        if payload["type"] != "access" or payload["otp_verified"] is not True:
            raise AccessTokenError("Unexpected token type")
        return AccessTokenClaims(
            user_id=UUID(str(payload["sub"])),
            tenant_id=UUID(str(payload["tenant_id"])),
            token_id=UUID(str(payload["jti"])),
            issued_at=_as_utc_datetime(payload["iat"]),
            otp_verified=True,
        )
    except AccessTokenError:
        raise
    except (KeyError, TypeError, ValueError, jwt.PyJWTError) as exc:
        raise AccessTokenError("Invalid access token") from exc


def _as_utc_datetime(value: Any) -> datetime:
    """Normalize PyJWT's numeric/date claim without widening trusted input."""

    if isinstance(value, datetime):
        return value.astimezone(UTC)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, UTC)
    raise AccessTokenError("Invalid access token")


def generate_refresh_token(tenant_id: UUID) -> str:
    """Create a tenant-addressable opaque credential with 256-bit entropy.

    The tenant UUID is an identifier, not a secret. Including it lets the
    refresh boundary establish PostgreSQL RLS before looking up the stored
    token hash.
    """

    return f"rt_{tenant_id}.{secrets.token_urlsafe(48)}"


def get_refresh_token_tenant_id(token: str) -> UUID:
    """Parse the non-secret tenant address from an opaque refresh token."""

    prefix, separator, _secret = token.partition(".")
    if separator != "." or not prefix.startswith("rt_") or not _secret:
        raise ValueError("Invalid refresh token format")
    return UUID(prefix.removeprefix("rt_"))


def hash_refresh_token(token: str) -> str:
    """Create the irreversible lookup value persisted for a refresh token."""

    return hashlib.sha256(token.encode("utf-8")).hexdigest()


__all__ = [
    "AccessTokenClaims",
    "AccessTokenError",
    "create_access_token",
    "decode_access_token",
    "dummy_password_hash",
    "generate_refresh_token",
    "get_refresh_token_tenant_id",
    "hash_password",
    "hash_refresh_token",
    "password_needs_rehash",
    "verify_password",
]
