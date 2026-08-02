from pydantic_settings import BaseSettings, SettingsConfigDict


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

    @property
    def is_local(self) -> bool:
        return self.APP_ENV in ("development", "test")


settings = Settings()  # type: ignore[call-arg]
