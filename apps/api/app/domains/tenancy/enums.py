"""Stable string values used by the tenancy tables."""

from enum import StrEnum


class UserStatus(StrEnum):
    """Lifecycle state for a global user identity."""

    ACTIVE = "active"
    DISABLED = "disabled"


class TenantStatus(StrEnum):
    """Lifecycle state for an organization."""

    ACTIVE = "active"
    SUSPENDED = "suspended"


class MembershipRole(StrEnum):
    """Authorization role within one tenant."""

    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


__all__ = ["MembershipRole", "TenantStatus", "UserStatus"]
