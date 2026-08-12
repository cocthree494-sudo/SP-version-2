"""Voice configuration contracts with explicit consent and cost controls."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domains.voice.models import VoiceStatus


class VoiceInstallRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    bot_id: UUID | None = None
    provider: str = Field(default="twilio", pattern=r"^(twilio|sip)$")
    phone_number: str = Field(min_length=3, max_length=32)
    language: str = Field(default="auto", min_length=2, max_length=16)
    voice: str = Field(default="alloy", min_length=2, max_length=64)
    business_hours: dict[str, object] = Field(default_factory=dict)
    outbound_enabled: bool = False
    recording_enabled: bool = False
    retention_days: int = Field(default=0, ge=0, le=365)
    monthly_cost_limit_usd: int = Field(default=100, ge=1, le=100000)
    consent_acknowledged: bool = False
    outbound_consent: bool = False
    recording_consent: bool = False

    @field_validator("phone_number")
    @classmethod
    def normalize_phone(cls, value: str) -> str:
        normalized = value.replace(" ", "").replace("-", "")
        if not normalized.startswith("+"):
            raise ValueError("Use an international phone number beginning with +")
        return normalized

    @model_validator(mode="after")
    def enforce_voice_consent(self) -> VoiceInstallRequest:
        if not self.consent_acknowledged:
            raise ValueError("Explicit voice-agent consent is required")
        if self.outbound_enabled and not self.outbound_consent:
            raise ValueError("Outbound calling requires separate consent")
        if self.recording_enabled and not self.recording_consent:
            raise ValueError("Call recording requires separate consent")
        if not self.recording_enabled and self.retention_days:
            raise ValueError("Retention days require call recording to be enabled")
        return self


class VoiceStatusUpdateRequest(BaseModel):
    status: VoiceStatus


class VoiceAgentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    bot_id: UUID | None
    provider: str
    phone_number: str
    language: str
    voice: str
    business_hours: dict[str, object]
    outbound_enabled: bool
    recording_enabled: bool
    retention_days: int
    monthly_cost_limit_usd: int
    status: VoiceStatus
    created_at: datetime
    updated_at: datetime


class VoiceWebhookRequest(BaseModel):
    event_id: str = Field(min_length=1, max_length=255)
    event_type: str = Field(min_length=1, max_length=64)
    payload: dict[str, object] = Field(default_factory=dict)


__all__ = [
    "VoiceAgentResponse",
    "VoiceInstallRequest",
    "VoiceStatusUpdateRequest",
    "VoiceWebhookRequest",
]
