"""Stable persisted enums for conversations and messages."""

from enum import StrEnum


class ConversationStatus(StrEnum):
    ACTIVE = "active"
    CLOSED = "closed"


class ConversationMessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


__all__ = ["ConversationMessageRole", "ConversationStatus"]

