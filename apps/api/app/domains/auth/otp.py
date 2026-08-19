"""Short-lived, single-use email OTP challenges."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass, replace
from typing import Any, Literal, Protocol, cast

from app.core.config import settings
from app.domains.auth.email import AuthEmailDeliveryError, AuthEmailSender

PendingAuthKind = Literal[
    "password_register",
    "password_login",
    "social_register",
    "social_login",
]


class AuthOtpError(RuntimeError):
    """Base class for safe OTP workflow failures."""


class AuthOtpUnavailableError(AuthOtpError):
    pass


class AuthOtpInvalidError(AuthOtpError):
    pass


class AuthOtpExpiredError(AuthOtpError):
    pass


class AuthOtpLockedError(AuthOtpError):
    pass


class AuthOtpRateLimitError(AuthOtpError):
    def __init__(self, message: str, *, retry_after: int) -> None:
        super().__init__(message)
        self.retry_after = retry_after


@dataclass(frozen=True, slots=True)
class PendingAuth:
    kind: PendingAuthKind
    email: str
    payload: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "email": self.email, "payload": self.payload}

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> PendingAuth:
        kind = value.get("kind")
        email = value.get("email")
        payload = value.get("payload")
        if kind not in {
            "password_register",
            "password_login",
            "social_register",
            "social_login",
        }:
            raise AuthOtpUnavailableError("The verification request is invalid")
        if not isinstance(email, str) or not isinstance(payload, dict):
            raise AuthOtpUnavailableError("The verification request is invalid")
        return cls(kind=cast(PendingAuthKind, kind), email=email, payload=payload)


@dataclass(frozen=True, slots=True)
class AuthOtpChallengeData:
    pending: PendingAuth
    otp_hash: str
    expires_at: int
    resend_available_at: int
    attempts: int
    max_attempts: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "pending": self.pending.as_dict(),
            "otp_hash": self.otp_hash,
            "expires_at": self.expires_at,
            "resend_available_at": self.resend_available_at,
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> AuthOtpChallengeData:
        pending = value.get("pending")
        required_numbers = (
            "expires_at",
            "resend_available_at",
            "attempts",
            "max_attempts",
        )
        if not isinstance(pending, dict) or not isinstance(value.get("otp_hash"), str):
            raise AuthOtpUnavailableError("The verification request is invalid")
        if any(not isinstance(value.get(key), int) for key in required_numbers):
            raise AuthOtpUnavailableError("The verification request is invalid")
        return cls(
            pending=PendingAuth.from_dict(pending),
            otp_hash=cast(str, value["otp_hash"]),
            expires_at=cast(int, value["expires_at"]),
            resend_available_at=cast(int, value["resend_available_at"]),
            attempts=cast(int, value["attempts"]),
            max_attempts=cast(int, value["max_attempts"]),
        )


@dataclass(frozen=True, slots=True)
class AuthOtpChallenge:
    challenge_id: str
    email_hint: str
    flow: Literal["login", "register"]
    expires_in: int
    resend_after: int


class AuthOtpStore(Protocol):
    async def put(
        self,
        challenge_id: str,
        value: AuthOtpChallengeData,
        ttl_seconds: int,
    ) -> None: ...

    async def get(self, challenge_id: str) -> AuthOtpChallengeData | None: ...

    async def delete(self, challenge_id: str) -> None: ...

    async def verify(
        self,
        challenge_id: str,
        candidate_hash: str,
        now: int,
    ) -> tuple[str, AuthOtpChallengeData | int | None]: ...

    async def allow_rate(self, key: str, limit: int, window_seconds: int) -> bool: ...


class InMemoryAuthOtpStore:
    """Deterministic fallback for unit tests and lightweight local checks."""

    def __init__(self) -> None:
        self._values: dict[str, tuple[AuthOtpChallengeData, int]] = {}
        self._rates: dict[str, tuple[int, int]] = {}
        self._lock = asyncio.Lock()

    async def put(
        self,
        challenge_id: str,
        value: AuthOtpChallengeData,
        ttl_seconds: int,
    ) -> None:
        async with self._lock:
            self._values[challenge_id] = (value, int(time.time()) + ttl_seconds)

    async def get(self, challenge_id: str) -> AuthOtpChallengeData | None:
        async with self._lock:
            stored = self._values.get(challenge_id)
            if stored is None:
                return None
            value, store_expires_at = stored
            if store_expires_at <= int(time.time()):
                self._values.pop(challenge_id, None)
                return None
            return value

    async def delete(self, challenge_id: str) -> None:
        async with self._lock:
            self._values.pop(challenge_id, None)

    async def verify(
        self,
        challenge_id: str,
        candidate_hash: str,
        now: int,
    ) -> tuple[str, AuthOtpChallengeData | int | None]:
        async with self._lock:
            stored = self._values.get(challenge_id)
            if stored is None:
                return "missing", None
            value, store_expires_at = stored
            if store_expires_at <= now or value.expires_at <= now:
                self._values.pop(challenge_id, None)
                return "expired", None
            if value.attempts >= value.max_attempts:
                self._values.pop(challenge_id, None)
                return "locked", None
            if not hmac.compare_digest(value.otp_hash, candidate_hash):
                attempts = value.attempts + 1
                if attempts >= value.max_attempts:
                    self._values.pop(challenge_id, None)
                    return "locked", None
                updated = replace(value, attempts=attempts)
                self._values[challenge_id] = (updated, store_expires_at)
                return "invalid", value.max_attempts - attempts
            self._values.pop(challenge_id, None)
            return "ok", value

    async def allow_rate(self, key: str, limit: int, window_seconds: int) -> bool:
        now = int(time.time())
        async with self._lock:
            count, expires_at = self._rates.get(key, (0, now + window_seconds))
            if expires_at <= now:
                count, expires_at = 0, now + window_seconds
            count += 1
            self._rates[key] = (count, expires_at)
            return count <= limit

    def clear(self) -> None:
        self._values.clear()
        self._rates.clear()


class RedisAuthOtpStore:
    """Redis-backed challenge store with atomic verify/consume behavior."""

    _verify_script = """
local raw = redis.call('GET', KEYS[1])
if not raw then return {'missing'} end
local data = cjson.decode(raw)
local now = tonumber(ARGV[2])
if tonumber(data.expires_at) <= now then
  redis.call('DEL', KEYS[1])
  return {'expired'}
end
local attempts = tonumber(data.attempts)
local maximum = tonumber(data.max_attempts)
if attempts >= maximum then
  redis.call('DEL', KEYS[1])
  return {'locked'}
end
if data.otp_hash ~= ARGV[1] then
  attempts = attempts + 1
  if attempts >= maximum then
    redis.call('DEL', KEYS[1])
    return {'locked'}
  end
  data.attempts = attempts
  local ttl = redis.call('PTTL', KEYS[1])
  redis.call('SET', KEYS[1], cjson.encode(data), 'PX', ttl)
  return {'invalid', tostring(maximum - attempts)}
end
redis.call('DEL', KEYS[1])
return {'ok', raw}
"""

    def __init__(self, redis: Any) -> None:
        self.redis = redis

    @staticmethod
    def _challenge_key(challenge_id: str) -> str:
        digest = hashlib.sha256(challenge_id.encode("ascii")).hexdigest()
        return f"support-agent:auth-otp:{digest}"

    async def put(
        self,
        challenge_id: str,
        value: AuthOtpChallengeData,
        ttl_seconds: int,
    ) -> None:
        await self.redis.set(
            self._challenge_key(challenge_id),
            json.dumps(value.as_dict(), separators=(",", ":")),
            ex=max(1, ttl_seconds),
        )

    async def get(self, challenge_id: str) -> AuthOtpChallengeData | None:
        raw = await self.redis.get(self._challenge_key(challenge_id))
        if raw is None:
            return None
        try:
            decoded = json.loads(raw)
            if not isinstance(decoded, dict):
                raise ValueError
            return AuthOtpChallengeData.from_dict(decoded)
        except (TypeError, ValueError, json.JSONDecodeError, AuthOtpError) as exc:
            await self.delete(challenge_id)
            raise AuthOtpUnavailableError("The verification request is invalid") from exc

    async def delete(self, challenge_id: str) -> None:
        await self.redis.delete(self._challenge_key(challenge_id))

    async def verify(
        self,
        challenge_id: str,
        candidate_hash: str,
        now: int,
    ) -> tuple[str, AuthOtpChallengeData | int | None]:
        result = await self.redis.eval(
            self._verify_script,
            1,
            self._challenge_key(challenge_id),
            candidate_hash,
            str(now),
        )
        if not isinstance(result, list) or not result:
            raise AuthOtpUnavailableError("The verification service is unavailable")
        status = result[0].decode() if isinstance(result[0], bytes) else str(result[0])
        if status == "ok" and len(result) == 2:
            raw = result[1].decode() if isinstance(result[1], bytes) else str(result[1])
            try:
                decoded = json.loads(raw)
                if not isinstance(decoded, dict):
                    raise ValueError
                return status, AuthOtpChallengeData.from_dict(decoded)
            except (TypeError, ValueError, json.JSONDecodeError, AuthOtpError) as exc:
                raise AuthOtpUnavailableError("The verification request is invalid") from exc
        if status == "invalid" and len(result) == 2:
            remaining = result[1].decode() if isinstance(result[1], bytes) else result[1]
            return status, int(remaining)
        return status, None

    async def allow_rate(self, key: str, limit: int, window_seconds: int) -> bool:
        redis_key = f"support-agent:auth-otp-rate:{key}"
        count = await self.redis.incr(redis_key)
        if count == 1:
            await self.redis.expire(redis_key, window_seconds)
        return int(count) <= limit


class AuthOtpService:
    def __init__(self, store: AuthOtpStore, sender: AuthEmailSender) -> None:
        self.store = store
        self.sender = sender

    async def start(self, pending: PendingAuth, *, client_ip: str) -> AuthOtpChallenge:
        delivery_email = self._delivery_email(pending)
        await self._enforce_rate_limits(delivery_email, client_ip)
        challenge_id = secrets.token_urlsafe(32)
        code = self._new_code()
        now = int(time.time())
        data = AuthOtpChallengeData(
            pending=pending,
            otp_hash=self._hash_otp(challenge_id, code),
            expires_at=now + settings.AUTH_OTP_TTL_SECONDS,
            resend_available_at=now + settings.AUTH_OTP_RESEND_COOLDOWN_SECONDS,
            attempts=0,
            max_attempts=settings.AUTH_OTP_MAX_ATTEMPTS,
        )
        await self._store_put(challenge_id, data, settings.AUTH_OTP_TTL_SECONDS)
        try:
            await self.sender.send_otp(
                email=delivery_email,
                code=code,
                expires_minutes=max(1, settings.AUTH_OTP_TTL_SECONDS // 60),
            )
        except AuthEmailDeliveryError:
            await self._store_delete(challenge_id)
            raise
        return self._metadata(challenge_id, data, now)

    async def status(self, challenge_id: str) -> AuthOtpChallenge:
        now = int(time.time())
        data = await self._store_get(challenge_id)
        if data is None:
            raise AuthOtpExpiredError("The verification request expired. Start again.")
        if data.expires_at <= now:
            await self._store_delete(challenge_id)
            raise AuthOtpExpiredError("The verification request expired. Start again.")
        return self._metadata(challenge_id, data, now)

    async def resend(self, challenge_id: str, *, client_ip: str) -> AuthOtpChallenge:
        now = int(time.time())
        data = await self._store_get(challenge_id)
        if data is None or data.expires_at <= now:
            await self._store_delete(challenge_id)
            raise AuthOtpExpiredError("The verification request expired. Start again.")
        if data.resend_available_at > now:
            retry_after = data.resend_available_at - now
            raise AuthOtpRateLimitError(
                "Please wait before requesting another code.",
                retry_after=retry_after,
            )
        delivery_email = self._delivery_email(data.pending)
        await self._enforce_rate_limits(delivery_email, client_ip)
        code = self._new_code()
        updated = replace(
            data,
            otp_hash=self._hash_otp(challenge_id, code),
            resend_available_at=now + settings.AUTH_OTP_RESEND_COOLDOWN_SECONDS,
            attempts=0,
        )
        await self._store_put(
            challenge_id,
            updated,
            max(1, updated.expires_at - now),
        )
        try:
            await self.sender.send_otp(
                email=delivery_email,
                code=code,
                expires_minutes=max(1, (updated.expires_at - now) // 60),
            )
        except AuthEmailDeliveryError:
            await self._store_delete(challenge_id)
            raise
        return self._metadata(challenge_id, updated, now)

    async def cancel(self, challenge_id: str) -> None:
        await self._store_delete(challenge_id)

    async def verify(self, challenge_id: str, code: str) -> PendingAuth:
        result, value = await self._store_verify(
            challenge_id,
            self._hash_otp(challenge_id, code),
            int(time.time()),
        )
        if result == "ok" and isinstance(value, AuthOtpChallengeData):
            return value.pending
        if result in {"missing", "expired"}:
            raise AuthOtpExpiredError("The verification request expired. Start again.")
        if result == "locked":
            raise AuthOtpLockedError("Too many incorrect codes. Start again.")
        if result == "invalid":
            remaining = value if isinstance(value, int) else 0
            raise AuthOtpInvalidError(
                f"That code is incorrect. {remaining} attempt(s) remaining."
            )
        raise AuthOtpUnavailableError("The verification service is unavailable")

    async def _enforce_rate_limits(self, email: str, client_ip: str) -> None:
        email_allowed = await self._store_allow_rate(
            self._rate_key("email", email.strip().casefold()),
            settings.AUTH_OTP_EMAIL_RATE_LIMIT,
            settings.AUTH_OTP_EMAIL_RATE_WINDOW_SECONDS,
        )
        ip_allowed = await self._store_allow_rate(
            self._rate_key("ip", client_ip.strip() or "unknown"),
            settings.AUTH_OTP_IP_RATE_LIMIT,
            settings.AUTH_OTP_IP_RATE_WINDOW_SECONDS,
        )
        if not email_allowed or not ip_allowed:
            raise AuthOtpRateLimitError(
                "Too many verification requests. Please try again later.",
                retry_after=min(
                    settings.AUTH_OTP_EMAIL_RATE_WINDOW_SECONDS,
                    settings.AUTH_OTP_IP_RATE_WINDOW_SECONDS,
                ),
            )

    @staticmethod
    def _delivery_email(pending: PendingAuth) -> str:
        """Route platform-admin challenges to the dedicated operator mailbox."""

        if pending.payload.get("admin_flow") is True:
            return settings.platform_admin_otp_email
        return pending.email

    async def _store_put(
        self,
        challenge_id: str,
        value: AuthOtpChallengeData,
        ttl_seconds: int,
    ) -> None:
        try:
            await self.store.put(challenge_id, value, ttl_seconds)
        except AuthOtpError:
            raise
        except Exception as exc:
            raise AuthOtpUnavailableError("The verification service is unavailable") from exc

    async def _store_get(self, challenge_id: str) -> AuthOtpChallengeData | None:
        try:
            return await self.store.get(challenge_id)
        except AuthOtpError:
            raise
        except Exception as exc:
            raise AuthOtpUnavailableError("The verification service is unavailable") from exc

    async def _store_delete(self, challenge_id: str) -> None:
        try:
            await self.store.delete(challenge_id)
        except AuthOtpError:
            raise
        except Exception as exc:
            raise AuthOtpUnavailableError("The verification service is unavailable") from exc

    async def _store_verify(
        self,
        challenge_id: str,
        candidate_hash: str,
        now: int,
    ) -> tuple[str, AuthOtpChallengeData | int | None]:
        try:
            return await self.store.verify(challenge_id, candidate_hash, now)
        except AuthOtpError:
            raise
        except Exception as exc:
            raise AuthOtpUnavailableError("The verification service is unavailable") from exc

    async def _store_allow_rate(self, key: str, limit: int, window_seconds: int) -> bool:
        try:
            return await self.store.allow_rate(key, limit, window_seconds)
        except AuthOtpError:
            raise
        except Exception as exc:
            raise AuthOtpUnavailableError("The verification service is unavailable") from exc

    @staticmethod
    def _email_hint(email: str) -> str:
        local, separator, domain = email.partition("@")
        if not separator:
            return "your email"
        visible = local[:1] if local else "*"
        return f"{visible}{'*' * max(3, len(local) - 1)}@{domain}"

    @staticmethod
    def _metadata(
        challenge_id: str,
        data: AuthOtpChallengeData,
        now: int,
    ) -> AuthOtpChallenge:
        return AuthOtpChallenge(
            challenge_id=challenge_id,
            email_hint=AuthOtpService._email_hint(AuthOtpService._delivery_email(data.pending)),
            flow=("register" if data.pending.kind.endswith("register") else "login"),
            expires_in=max(0, data.expires_at - now),
            resend_after=max(0, data.resend_available_at - now),
        )

    @staticmethod
    def _hash_otp(challenge_id: str, code: str) -> str:
        message = f"relay-auth-otp:{challenge_id}:{code}".encode()
        return hmac.new(
            settings.auth_otp_secret.encode("utf-8"),
            message,
            hashlib.sha256,
        ).hexdigest()

    @staticmethod
    def _new_code() -> str:
        configured = settings.AUTH_OTP_TEST_CODE
        if settings.APP_ENV == "test" and configured is not None:
            return configured.get_secret_value()
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"
        while True:
            code = "".join(secrets.choice(alphabet) for _ in range(8))
            if any(character.isalpha() for character in code) and any(
                character.isdigit() for character in code
            ):
                return code

    @staticmethod
    def _rate_key(scope: str, value: str) -> str:
        digest = hmac.new(
            settings.auth_otp_secret.encode("utf-8"),
            f"relay-auth-rate:{scope}:{value}".encode(),
            hashlib.sha256,
        ).hexdigest()
        return f"{scope}:{digest}"


__all__ = [
    "AuthOtpChallenge",
    "AuthOtpError",
    "AuthOtpExpiredError",
    "AuthOtpInvalidError",
    "AuthOtpLockedError",
    "AuthOtpRateLimitError",
    "AuthOtpService",
    "AuthOtpStore",
    "AuthOtpUnavailableError",
    "InMemoryAuthOtpStore",
    "PendingAuth",
    "PendingAuthKind",
    "RedisAuthOtpStore",
]
