"""Owner/admin API for write-only tenant generation credentials and policy."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import AuthContext, CurrentAuth
from app.core.envelope import (
    EnvelopeCipher,
    SecretEnvelopeError,
    configured_envelope_cipher,
)
from app.db.session import get_db_session
from app.domains.provider_access.schemas import (
    ProviderCredentialCreateRequest,
    ProviderCredentialResponse,
    ProviderCredentialRotateRequest,
    ProviderPolicyResponse,
    ProviderPolicyUpdateRequest,
)
from app.domains.provider_access.service import (
    CredentialVerifier,
    DuplicateProviderCredentialError,
    InvalidProviderPolicyError,
    ProviderAccessService,
    ProviderCredentialNotFoundError,
    ProviderCredentialRevokedError,
    ProviderCredentialVerificationError,
)
from app.domains.tenancy.enums import MembershipRole
from app.providers.tenant_factory import LiveCredentialVerifier

router = APIRouter(prefix="/v1/providers", tags=["providers"])
DbSession = Annotated[AsyncSession, Depends(get_db_session)]


def require_provider_manager(context: CurrentAuth) -> AuthContext:
    if context.membership.role not in {MembershipRole.OWNER, MembershipRole.ADMIN}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Owner or admin role is required",
        )
    return context


def get_provider_envelope_cipher() -> EnvelopeCipher:
    try:
        return configured_envelope_cipher()
    except SecretEnvelopeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from None


def get_credential_verifier() -> CredentialVerifier:
    return LiveCredentialVerifier()


ProviderManager = Annotated[AuthContext, Depends(require_provider_manager)]
CipherDependency = Annotated[EnvelopeCipher, Depends(get_provider_envelope_cipher)]
VerifierDependency = Annotated[CredentialVerifier, Depends(get_credential_verifier)]


def _service(
    session: AsyncSession,
    context: AuthContext,
    cipher: EnvelopeCipher,
) -> ProviderAccessService:
    return ProviderAccessService(session, context.tenant.id, cipher=cipher)


def _domain_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ProviderCredentialNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, ProviderCredentialVerificationError):
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.post(
    "/credentials",
    response_model=ProviderCredentialResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_credential(
    payload: ProviderCredentialCreateRequest,
    session: DbSession,
    context: ProviderManager,
    cipher: CipherDependency,
) -> ProviderCredentialResponse:
    try:
        credential = await _service(session, context, cipher).create(payload)
    except DuplicateProviderCredentialError as exc:
        raise _domain_error(exc) from None
    return ProviderCredentialResponse.model_validate(credential)


@router.get("/credentials", response_model=list[ProviderCredentialResponse])
async def list_credentials(
    session: DbSession,
    context: ProviderManager,
    cipher: CipherDependency,
) -> list[ProviderCredentialResponse]:
    credentials = await _service(session, context, cipher).list()
    return [ProviderCredentialResponse.model_validate(item) for item in credentials]


@router.post(
    "/credentials/{credential_id}/verify",
    response_model=ProviderCredentialResponse,
)
async def verify_credential(
    credential_id: UUID,
    session: DbSession,
    context: ProviderManager,
    cipher: CipherDependency,
    verifier: VerifierDependency,
) -> ProviderCredentialResponse:
    try:
        credential = await _service(session, context, cipher).verify(
            credential_id,
            verifier,
        )
    except (
        ProviderCredentialNotFoundError,
        ProviderCredentialRevokedError,
        ProviderCredentialVerificationError,
    ) as exc:
        raise _domain_error(exc) from None
    return ProviderCredentialResponse.model_validate(credential)


@router.put(
    "/credentials/{credential_id}/secret",
    response_model=ProviderCredentialResponse,
)
async def rotate_credential(
    credential_id: UUID,
    payload: ProviderCredentialRotateRequest,
    session: DbSession,
    context: ProviderManager,
    cipher: CipherDependency,
) -> ProviderCredentialResponse:
    try:
        credential = await _service(session, context, cipher).rotate(
            credential_id,
            payload.api_key,
        )
    except (
        DuplicateProviderCredentialError,
        ProviderCredentialNotFoundError,
        ProviderCredentialRevokedError,
    ) as exc:
        raise _domain_error(exc) from None
    return ProviderCredentialResponse.model_validate(credential)


@router.delete("/credentials/{credential_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_credential(
    credential_id: UUID,
    session: DbSession,
    context: ProviderManager,
    cipher: CipherDependency,
) -> Response:
    try:
        await _service(session, context, cipher).revoke(credential_id)
    except ProviderCredentialNotFoundError as exc:
        raise _domain_error(exc) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/policy", response_model=ProviderPolicyResponse)
async def get_policy(
    session: DbSession,
    context: ProviderManager,
    cipher: CipherDependency,
) -> ProviderPolicyResponse:
    policy = await _service(session, context, cipher).get_policy()
    return ProviderPolicyResponse(
        mode=policy.mode,
        credential_order=policy.credential_order,
    )


@router.patch("/policy", response_model=ProviderPolicyResponse)
async def update_policy(
    payload: ProviderPolicyUpdateRequest,
    session: DbSession,
    context: ProviderManager,
    cipher: CipherDependency,
) -> ProviderPolicyResponse:
    try:
        policy = await _service(session, context, cipher).update_policy(payload)
    except InvalidProviderPolicyError as exc:
        raise _domain_error(exc) from None
    return ProviderPolicyResponse(
        mode=policy.mode,
        credential_order=policy.credential_order,
    )


__all__ = [
    "get_credential_verifier",
    "get_provider_envelope_cipher",
    "require_provider_manager",
    "router",
]
