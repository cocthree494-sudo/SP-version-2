"""Fail-closed repositories for tenant provider credentials and policy."""

from __future__ import annotations

from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import (
    TenantContextError,
    get_current_tenant_id,
    maybe_current_tenant_id,
    set_database_tenant,
)
from app.domains.provider_access.enums import GenerationProvider, ProviderRoutingMode
from app.domains.provider_access.models import ProviderCredential, ProviderPolicy


class _TenantRepository:
    def __init__(self, session: AsyncSession, tenant_id: UUID | None = None) -> None:
        self.session = session
        self._tenant_id = tenant_id

    def _resolve_tenant_id(self) -> UUID:
        active = maybe_current_tenant_id()
        if self._tenant_id is not None:
            if active is not None and active != self._tenant_id:
                raise TenantContextError("Repository tenant does not match active tenant context")
            return self._tenant_id
        return get_current_tenant_id()

    async def _prepare_scope(self) -> UUID:
        tenant_id = self._resolve_tenant_id()
        await set_database_tenant(self.session, tenant_id)
        return tenant_id


class ProviderCredentialRepository(_TenantRepository):
    async def create(
        self,
        *,
        credential_id: UUID,
        provider: GenerationProvider,
        label: str,
        base_url: str | None,
        encrypted_secret: str,
        wrapped_data_key: str,
        key_version: str,
        masked_secret: str,
        fingerprint: str,
        low_cost_model_id: str,
        strong_model_id: str | None,
    ) -> ProviderCredential:
        tenant_id = await self._prepare_scope()
        credential = ProviderCredential(
            id=credential_id,
            tenant_id=tenant_id,
            provider=provider,
            label=label,
            base_url=base_url,
            encrypted_secret=encrypted_secret,
            wrapped_data_key=wrapped_data_key,
            key_version=key_version,
            masked_secret=masked_secret,
            fingerprint=fingerprint,
            low_cost_model_id=low_cost_model_id,
            strong_model_id=strong_model_id,
        )
        self.session.add(credential)
        await self.session.flush()
        return credential

    async def list_all(self) -> list[ProviderCredential]:
        tenant_id = await self._prepare_scope()
        result = await self.session.scalars(
            select(ProviderCredential)
            .where(ProviderCredential.tenant_id == tenant_id)
            .order_by(ProviderCredential.created_at, ProviderCredential.id)
        )
        return list(result)

    async def get(
        self,
        credential_id: UUID,
        *,
        for_update: bool = False,
    ) -> ProviderCredential | None:
        tenant_id = await self._prepare_scope()
        query = select(ProviderCredential).where(
            ProviderCredential.id == credential_id,
            ProviderCredential.tenant_id == tenant_id,
        )
        if for_update:
            query = query.with_for_update()
        return cast(ProviderCredential | None, await self.session.scalar(query))

    async def get_ordered(self, credential_ids: list[UUID]) -> list[ProviderCredential]:
        if not credential_ids:
            return []
        tenant_id = await self._prepare_scope()
        result = await self.session.scalars(
            select(ProviderCredential).where(
                ProviderCredential.tenant_id == tenant_id,
                ProviderCredential.id.in_(credential_ids),
            )
        )
        by_id = {credential.id: credential for credential in result}
        return [by_id[item] for item in credential_ids if item in by_id]


class ProviderPolicyRepository(_TenantRepository):
    async def get(self, *, for_update: bool = False) -> ProviderPolicy | None:
        tenant_id = await self._prepare_scope()
        query = select(ProviderPolicy).where(ProviderPolicy.tenant_id == tenant_id)
        if for_update:
            query = query.with_for_update()
        return cast(ProviderPolicy | None, await self.session.scalar(query))

    async def upsert(
        self,
        *,
        mode: ProviderRoutingMode,
        credential_order: list[UUID],
    ) -> ProviderPolicy:
        tenant_id = await self._prepare_scope()
        policy = await self.get(for_update=True)
        serialized = [str(item) for item in credential_order]
        if policy is None:
            policy = ProviderPolicy(
                tenant_id=tenant_id,
                mode=mode,
                credential_order=serialized,
            )
            self.session.add(policy)
        else:
            policy.mode = mode
            policy.credential_order = serialized
        await self.session.flush()
        return policy


__all__ = ["ProviderCredentialRepository", "ProviderPolicyRepository"]
