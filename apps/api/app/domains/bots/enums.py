"""Stable lifecycle values for support bots."""

from enum import StrEnum


class BotStatus(StrEnum):
    """Whether a bot can accept public widget traffic."""

    ACTIVE = "active"
    DISABLED = "disabled"


__all__ = ["BotStatus"]
