"""Safe, channel-neutral installation contracts.

External access tokens and OTPs never cross this API. Connectors exchange
those secrets in their provider-owned flow and persist only an opaque
credential reference here.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domains.channels.models import ChannelStatus, ChannelType


class ChannelInstallRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    channel_type: ChannelType
    bot_id: UUID
    external_identity: str = Field(min_length=1, max_length=255)
    conversation_scope: list[str] = Field(default_factory=list, max_length=100)
    consent_acknowledged: bool = False

    @field_validator("external_identity")
    @classmethod
    def normalize_identity(cls, value: str) -> str:
        return value.strip()

    @field_validator("conversation_scope")
    @classmethod
    def normalize_scope(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value if item.strip()]
        if len(set(normalized)) != len(normalized):
            raise ValueError("conversation_scope cannot contain duplicates")
        if any(len(item) > 255 for item in normalized):
            raise ValueError("conversation_scope entries must be 255 characters or fewer")
        return normalized

    @model_validator(mode="after")
    def enforce_connection_rules(self) -> ChannelInstallRequest:
        if not self.consent_acknowledged:
            raise ValueError("Explicit channel access consent is required")
        if (
            self.channel_type is ChannelType.WHATSAPP_BUSINESS
            and not self.external_identity.startswith("business:")
        ):
            raise ValueError("WhatsApp requires an official Business account identity")
        if self.channel_type is ChannelType.FACEBOOK_PAGE and not self.external_identity.startswith(
            "page:"
        ):
            raise ValueError("Facebook Messenger requires a tenant-owned Page identity")
        if (
            self.channel_type is ChannelType.TELEGRAM_PERSONAL
            and not self.external_identity.startswith("telegram:")
        ):
            raise ValueError("Telegram personal connectors require a Telegram identity")
        return self


class ChannelStatusUpdateRequest(BaseModel):
    status: ChannelStatus | None = None
    bot_id: UUID | None = None

    @model_validator(mode="after")
    def require_a_change(self) -> ChannelStatusUpdateRequest:
        if self.status is None and self.bot_id is None:
            raise ValueError("Choose a bot or status to update")
        return self


class ChannelInstallationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    bot_id: UUID | None
    channel_type: ChannelType
    external_identity: str
    status: ChannelStatus
    conversation_scope: list[str]
    consent_record: dict[str, object]
    expires_at: datetime | None
    created_at: datetime
    updated_at: datetime


__all__ = [
    "ChannelInstallRequest",
    "ChannelInstallationResponse",
    "ChannelStatusUpdateRequest",
]
