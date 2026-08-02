import secrets
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ephemeral_local_auth_secret = SecretStr(secrets.token_urlsafe(48))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_ignore_empty=True, extra="ignore"
    )

    APP_ENV: str = "development"
    API_HOST: str = "127.0.0.1"
    API_PORT: int = 8000

    # PostgreSQL
    POSTGRES_DB: str = "support_agent"
    POSTGRES_USER: str = "support_agent"
    POSTGRES_PASSWORD: str = "support_agent_local"  # noqa: S105
    POSTGRES_PORT: int = 5432
    DATABASE_URL: str

    # Redis
    REDIS_PORT: int = 6379
    REDIS_URL: str

    # Authentication. Local/test processes get an ephemeral fallback so
    # imports and CI checks do not require a committed secret. Production must
    # always supply AUTH_JWT_SECRET through its secret manager.
    AUTH_JWT_SECRET: SecretStr | None = None
    AUTH_JWT_ALGORITHM: Literal["HS256", "HS384", "HS512"] = "HS256"
    AUTH_JWT_ISSUER: str = "support-agent-api"
    AUTH_JWT_AUDIENCE: str = "support-agent-dashboard"
    AUTH_ACCESS_TOKEN_TTL_SECONDS: int = Field(default=900, ge=60, le=3600)
    AUTH_REFRESH_TOKEN_TTL_DAYS: int = Field(default=30, ge=1, le=90)

    @model_validator(mode="after")
    def require_production_auth_secret(self) -> "Settings":
        if not self.is_local and self.AUTH_JWT_SECRET is None:
            raise ValueError("AUTH_JWT_SECRET is required outside development and test")
        if self.AUTH_JWT_SECRET is not None:
            secret = self.AUTH_JWT_SECRET.get_secret_value()
            if len(secret) < 32:
                raise ValueError("AUTH_JWT_SECRET must contain at least 32 characters")
        return self

    @property
    def is_local(self) -> bool:
        return self.APP_ENV in ("development", "test")

    @property
    def auth_jwt_secret(self) -> str:
        configured = self.AUTH_JWT_SECRET or _ephemeral_local_auth_secret
        return configured.get_secret_value()


settings = Settings()  # type: ignore[call-arg]
