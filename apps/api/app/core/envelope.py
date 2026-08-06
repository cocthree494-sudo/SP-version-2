"""Provider-neutral envelope encryption for recoverable tenant API keys."""

from __future__ import annotations

import base64
import hashlib
import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import SecretStr

from app.core.config import settings


class SecretEnvelopeError(RuntimeError):
    """Safe base error that never contains credential material."""


class SecretEncryptionUnavailableError(SecretEnvelopeError):
    """Raised when BYOK custody has not been configured."""


class SecretDecryptionError(SecretEnvelopeError):
    """Raised when an envelope is corrupt or its wrapping key is unavailable."""


@dataclass(frozen=True, slots=True)
class EncryptedEnvelope:
    ciphertext: str
    wrapped_data_key: str
    key_version: str


class KeyWrapper(Protocol):
    key_version: str

    def wrap(self, data_key: bytes, *, aad: bytes) -> str: ...

    def unwrap(self, wrapped_data_key: str, *, aad: bytes) -> bytes: ...


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii")


def _decode(value: str) -> bytes:
    try:
        return base64.urlsafe_b64decode(value.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise SecretDecryptionError("Tenant credential envelope is invalid") from exc


class LocalAesGcmKeyWrapper:
    """Development adapter; a cloud KMS/Vault wrapper can replace this protocol."""

    def __init__(self, master_key: bytes, *, key_version: str) -> None:
        if len(master_key) != 32:
            raise ValueError("Envelope master key must contain exactly 32 bytes")
        self._cipher = AESGCM(master_key)
        self.key_version = key_version

    def wrap(self, data_key: bytes, *, aad: bytes) -> str:
        nonce = os.urandom(12)
        wrapped = self._cipher.encrypt(nonce, data_key, aad + self.key_version.encode())
        return _encode(nonce + wrapped)

    def unwrap(self, wrapped_data_key: str, *, aad: bytes) -> bytes:
        payload = _decode(wrapped_data_key)
        if len(payload) < 29:
            raise SecretDecryptionError("Tenant credential envelope is invalid")
        try:
            return self._cipher.decrypt(
                payload[:12],
                payload[12:],
                aad + self.key_version.encode(),
            )
        except InvalidTag as exc:
            raise SecretDecryptionError("Tenant credential envelope cannot be decrypted") from exc


class EnvelopeCipher:
    """Encrypt each secret with a random data key, then wrap that key separately."""

    def __init__(self, key_wrapper: KeyWrapper) -> None:
        self._key_wrapper = key_wrapper

    def encrypt(self, secret: SecretStr, *, aad: bytes) -> EncryptedEnvelope:
        data_key = AESGCM.generate_key(bit_length=256)
        nonce = os.urandom(12)
        plaintext = secret.get_secret_value().encode("utf-8")
        ciphertext = AESGCM(data_key).encrypt(nonce, plaintext, aad)
        return EncryptedEnvelope(
            ciphertext=_encode(nonce + ciphertext),
            wrapped_data_key=self._key_wrapper.wrap(data_key, aad=aad),
            key_version=self._key_wrapper.key_version,
        )

    def decrypt(self, envelope: EncryptedEnvelope, *, aad: bytes) -> SecretStr:
        if envelope.key_version != self._key_wrapper.key_version:
            raise SecretDecryptionError("Tenant credential key version is unavailable")
        payload = _decode(envelope.ciphertext)
        if len(payload) < 29:
            raise SecretDecryptionError("Tenant credential envelope is invalid")
        data_key = self._key_wrapper.unwrap(envelope.wrapped_data_key, aad=aad)
        try:
            plaintext = AESGCM(data_key).decrypt(payload[:12], payload[12:], aad)
            return SecretStr(plaintext.decode("utf-8"))
        except (InvalidTag, UnicodeDecodeError) as exc:
            raise SecretDecryptionError("Tenant credential envelope cannot be decrypted") from exc


def credential_aad(tenant_id: UUID, credential_id: UUID, provider: str) -> bytes:
    return f"support-agent/byok/{tenant_id}/{credential_id}/{provider}".encode()


def credential_fingerprint(tenant_id: UUID, secret: SecretStr) -> str:
    digest = hashlib.sha256()
    digest.update(tenant_id.bytes)
    digest.update(secret.get_secret_value().encode("utf-8"))
    return digest.hexdigest()


def masked_secret(secret: SecretStr) -> str:
    value = secret.get_secret_value()
    suffix = value[-4:] if len(value) >= 4 else "****"
    return f"••••{suffix}"


@lru_cache(maxsize=1)
def configured_envelope_cipher() -> EnvelopeCipher:
    if settings.BYOK_MASTER_KEY is None:
        raise SecretEncryptionUnavailableError(
            "Tenant provider credential storage is not configured"
        )
    master_key = _decode(settings.BYOK_MASTER_KEY.get_secret_value())
    return EnvelopeCipher(
        LocalAesGcmKeyWrapper(master_key, key_version=settings.BYOK_MASTER_KEY_VERSION)
    )


__all__ = [
    "EncryptedEnvelope",
    "EnvelopeCipher",
    "KeyWrapper",
    "LocalAesGcmKeyWrapper",
    "SecretDecryptionError",
    "SecretEncryptionUnavailableError",
    "SecretEnvelopeError",
    "configured_envelope_cipher",
    "credential_aad",
    "credential_fingerprint",
    "masked_secret",
]
