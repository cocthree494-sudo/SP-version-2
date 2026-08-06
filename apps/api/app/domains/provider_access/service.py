"""Encrypted credential lifecycle and explicit tenant routing policy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID, uuid4

from pydantic import SecretStr
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.envelope import (
    EncryptedEnvelope,
    EnvelopeCipher,
    credential_aad,
    credential_fingerprint,
    masked_secret,
)
from app.db.base import utc_now
from app.domains.provider_access.enums import (
    GenerationProvider,
    ProviderCredentialStatus,
    ProviderRoutingMode,
)
from app.domains.provider_access.models import ProviderCredential
from app.domains.provider_access.repositories import (
    ProviderCredentialRepository,
    ProviderPolicyRepository,
)
from app.domains.provider_access.schemas import (
    ProviderCredentialCreateRequest,
    ProviderPolicyUpdateRequest,
)
from app.providers.types import ProviderError


class ProviderAccessError(RuntimeError):
    """Base class for safe expected provider-access failures."""


class ProviderCredentialNotFoundError(ProviderAccessError):
    pass


class ProviderCredentialRevokedError(ProviderAccessError):
    pass


class DuplicateProviderCredentialError(ProviderAccessError):
    pass


class ProviderCredentialVerificationError(ProviderAccessError):
    pass


class InvalidProviderPolicyError(ProviderAccessError):
    pass


class CredentialVerifier(Protocol):
    async def verify(
        self,
        *,
        provider: GenerationProvider,
        model_id: str,
        secret: SecretStr,
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class ProviderPolicyView:
    mode: ProviderRoutingMode
    credential_order: list[UUID]


class ProviderAccessService:
    def __init__(
        self,
        session: AsyncSession,
        tenant_id: UUID,
        *,
        cipher: EnvelopeCipher,
    ) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.cipher = cipher
        self.credentials = ProviderCredentialRepository(session, tenant_id)
        self.policies = ProviderPolicyRepository(session, tenant_id)

    def _aad(self, credential_id: UUID, provider: GenerationProvider) -> bytes:
        return credential_aad(self.tenant_id, credential_id, provider.value)

    def decrypt(self, credential: ProviderCredential) -> SecretStr:
        return self.cipher.decrypt(
            EncryptedEnvelope(
                ciphertext=credential.encrypted_secret,
                wrapped_data_key=credential.wrapped_data_key,
                key_version=credential.key_version,
            ),
            aad=self._aad(credential.id, credential.provider),
        )

    async def create(self, payload: ProviderCredentialCreateRequest) -> ProviderCredential:
        credential_id = uuid4()
        envelope = self.cipher.encrypt(
            payload.api_key,
            aad=self._aad(credential_id, payload.provider),
        )
        try:
            credential = await self.credentials.create(
                credential_id=credential_id,
                provider=payload.provider,
                label=payload.label,
                encrypted_secret=envelope.ciphertext,
                wrapped_data_key=envelope.wrapped_data_key,
                key_version=envelope.key_version,
                masked_secret=masked_secret(payload.api_key),
                fingerprint=credential_fingerprint(self.tenant_id, payload.api_key),
                low_cost_model_id=payload.low_cost_model_id,
                strong_model_id=payload.strong_model_id,
            )
            await self.session.commit()
            return credential
        except IntegrityError as exc:
            await self.session.rollback()
            raise DuplicateProviderCredentialError(
                "This provider credential is already registered for the organization"
            ) from exc

    async def list(self) -> list[ProviderCredential]:
        return await self.credentials.list_all()

    async def get(self, credential_id: UUID, *, for_update: bool = False) -> ProviderCredential:
        credential = await self.credentials.get(credential_id, for_update=for_update)
        if credential is None:
            raise ProviderCredentialNotFoundError("Provider credential not found")
        return credential

    async def verify(
        self,
        credential_id: UUID,
        verifier: CredentialVerifier,
    ) -> ProviderCredential:
        credential = await self.get(credential_id, for_update=True)
        if credential.status is ProviderCredentialStatus.REVOKED:
            raise ProviderCredentialRevokedError("A revoked provider credential cannot be verified")
        secret = self.decrypt(credential)
        try:
            await verifier.verify(
                provider=credential.provider,
                model_id=credential.low_cost_model_id,
                secret=secret,
            )
        except ProviderError as exc:
            credential.status = ProviderCredentialStatus.INVALID
            credential.verified_at = None
            await self.session.commit()
            raise ProviderCredentialVerificationError(
                f"Provider credential verification failed ({exc.category.value})"
            ) from None
        credential.status = ProviderCredentialStatus.VERIFIED
        credential.verified_at = utc_now()
        await self.session.commit()
        return credential

    async def rotate(self, credential_id: UUID, secret: SecretStr) -> ProviderCredential:
        credential = await self.get(credential_id, for_update=True)
        if credential.status is ProviderCredentialStatus.REVOKED:
            raise ProviderCredentialRevokedError("A revoked provider credential cannot be rotated")
        envelope = self.cipher.encrypt(
            secret,
            aad=self._aad(credential.id, credential.provider),
        )
        credential.encrypted_secret = envelope.ciphertext
        credential.wrapped_data_key = envelope.wrapped_data_key
        credential.key_version = envelope.key_version
        credential.masked_secret = masked_secret(secret)
        credential.fingerprint = credential_fingerprint(self.tenant_id, secret)
        credential.status = ProviderCredentialStatus.UNVERIFIED
        credential.verified_at = None
        credential.rotated_at = utc_now()
        try:
            await self.session.commit()
            return credential
        except IntegrityError as exc:
            await self.session.rollback()
            raise DuplicateProviderCredentialError(
                "This provider credential is already registered for the organization"
            ) from exc

    async def revoke(self, credential_id: UUID) -> None:
        credential = await self.get(credential_id, for_update=True)
        if credential.status is not ProviderCredentialStatus.REVOKED:
            credential.status = ProviderCredentialStatus.REVOKED
            credential.revoked_at = utc_now()
            policy = await self.policies.get(for_update=True)
            if policy is not None:
                revoked_id = str(credential.id)
                policy.credential_order = [
                    item for item in policy.credential_order if item != revoked_id
                ]
            await self.session.commit()

    async def get_policy(self) -> ProviderPolicyView:
        policy = await self.policies.get()
        if policy is None:
            return ProviderPolicyView(ProviderRoutingMode.PLATFORM_ONLY, [])
        return ProviderPolicyView(
            mode=policy.mode,
            credential_order=[UUID(item) for item in policy.credential_order],
        )

    async def update_policy(self, payload: ProviderPolicyUpdateRequest) -> ProviderPolicyView:
        if payload.mode is ProviderRoutingMode.PLATFORM_ONLY:
            ordered_ids: list[UUID] = []
        else:
            ordered_ids = payload.credential_order
            credentials = await self.credentials.get_ordered(ordered_ids)
            if len(credentials) != len(ordered_ids):
                raise InvalidProviderPolicyError(
                    "Routing policy contains a provider credential that was not found"
                )
            if any(
                item.status is not ProviderCredentialStatus.VERIFIED for item in credentials
            ):
                raise InvalidProviderPolicyError(
                    "Only verified, active provider credentials can be routed"
                )
        policy = await self.policies.upsert(
            mode=payload.mode,
            credential_order=ordered_ids,
        )
        await self.session.commit()
        return ProviderPolicyView(
            mode=policy.mode,
            credential_order=[UUID(item) for item in policy.credential_order],
        )


__all__ = [
    "CredentialVerifier",
    "DuplicateProviderCredentialError",
    "InvalidProviderPolicyError",
    "ProviderAccessError",
    "ProviderAccessService",
    "ProviderCredentialNotFoundError",
    "ProviderCredentialRevokedError",
    "ProviderCredentialVerificationError",
    "ProviderPolicyView",
]
