import secrets
from pathlib import Path
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
    # A deliberately weaker connection is required for meaningful RLS tests.
    # The migration owner in DATABASE_URL can bypass row-level security.
    TEST_DATABASE_URL: str | None = None

    # Redis
    REDIS_PORT: int = 6379
    REDIS_URL: str

    # Object storage. The local adapter is the development default; production
    # can provide an S3-compatible implementation of the same interface.
    LOCAL_STORAGE_ROOT: Path = Path(".data/uploads")
    FILE_UPLOAD_MAX_BYTES: int = Field(default=20 * 1024 * 1024, ge=1024, le=100 * 1024 * 1024)
    FILE_UPLOAD_CHUNK_BYTES: int = Field(default=64 * 1024, ge=4096, le=1024 * 1024)
    FILE_PARSE_MAX_PAGES: int = Field(default=1000, ge=1, le=10000)
    FILE_PARSE_MAX_OUTPUT_CHARS: int = Field(default=5_000_000, ge=1000, le=50_000_000)
    DOCX_MAX_UNCOMPRESSED_BYTES: int = Field(
        default=100 * 1024 * 1024,
        ge=1024,
        le=500 * 1024 * 1024,
    )
    CHUNK_MAX_TOKENS: int = Field(default=400, ge=32, le=4000)
    CHUNK_OVERLAP_TOKENS: int = Field(default=60, ge=0, le=1000)
    EMBEDDING_BATCH_SIZE: int = Field(default=32, ge=1, le=256)
    EMBEDDING_PROVIDER_ID: str = "deterministic"
    EMBEDDING_MODEL_ID: str = "deterministic-embedding-v1"
    EMBEDDING_DIMENSIONS: int = Field(default=32, ge=8, le=4096)
    WEBSITE_CRAWL_MAX_PAGES: int = Field(default=50, ge=1, le=500)
    WEBSITE_CRAWL_MAX_DEPTH: int = Field(default=3, ge=0, le=10)
    WEBSITE_CRAWL_REQUEST_DELAY_SECONDS: float = Field(default=0.25, ge=0.0, le=10.0)
    WEBSITE_CRAWL_TIMEOUT_SECONDS: float = Field(default=15.0, ge=1.0, le=120.0)
    WEBSITE_CRAWL_MAX_RESPONSE_BYTES: int = Field(
        default=2 * 1024 * 1024,
        ge=1024,
        le=20 * 1024 * 1024,
    )
    WEBSITE_CRAWL_MAX_REDIRECTS: int = Field(default=5, ge=0, le=10)
    WEBSITE_CRAWL_USER_AGENT: str = "SupportAgentBot/0.1"
    RETRIEVAL_CANDIDATE_LIMIT: int = Field(default=40, ge=5, le=500)
    RETRIEVAL_RRF_K: int = Field(default=60, ge=1, le=1000)
    RETRIEVAL_VECTOR_WEIGHT: float = Field(default=1.0, ge=0.0, le=10.0)
    RETRIEVAL_LEXICAL_WEIGHT: float = Field(default=1.0, ge=0.0, le=10.0)

    # Provider-neutral AI configuration. IDs remain environment configuration.
    AI_PROVIDER_MODE: Literal["deterministic", "openai_compatible"] = "deterministic"
    AI_PROVIDER_ID: str = "deterministic"
    AI_BASE_URL: str | None = None
    AI_API_KEY: SecretStr | None = None
    AI_REQUEST_TIMEOUT_SECONDS: float = Field(default=30.0, ge=1.0, le=300.0)
    LLM_MODEL_ID: str = "deterministic-chat-v1"
    LLM_STRONG_MODEL_ID: str | None = "deterministic-chat-strong-v1"
    DETERMINISTIC_LLM_RESPONSE: str = "Deterministic support response."
    MODEL_ROUTER_MAX_RETRIES_PER_TARGET: int = Field(default=1, ge=0, le=5)
    MODEL_ROUTER_RETRY_BASE_SECONDS: float = Field(default=0.1, ge=0.0, le=10.0)
    MODEL_ROUTER_TOTAL_TIMEOUT_SECONDS: float = Field(default=60.0, ge=1.0, le=600.0)
    MODEL_ROUTER_CIRCUIT_FAILURE_THRESHOLD: int = Field(default=3, ge=1, le=20)
    MODEL_ROUTER_CIRCUIT_COOLDOWN_SECONDS: int = Field(default=60, ge=1, le=3600)
    MODEL_ROUTER_WEAK_RETRIEVAL_SCORE: float = Field(default=0.012, ge=0.0, le=1.0)
    MODEL_ROUTER_COMPLEXITY_THRESHOLD: float = Field(default=0.7, ge=0.0, le=1.0)
    LLM_INPUT_COST_MICROUSD_PER_MILLION: int = Field(default=0, ge=0)
    LLM_OUTPUT_COST_MICROUSD_PER_MILLION: int = Field(default=0, ge=0)
    LLM_STRONG_INPUT_COST_MICROUSD_PER_MILLION: int = Field(default=0, ge=0)
    LLM_STRONG_OUTPUT_COST_MICROUSD_PER_MILLION: int = Field(default=0, ge=0)

    # Conversation continuity and retention. Retention is refreshed whenever
    # a message is appended; compaction preserves recent verbatim turns.
    CONVERSATION_RECENT_MESSAGE_LIMIT: int = Field(default=12, ge=1, le=100)
    CONVERSATION_MESSAGE_MAX_CHARS: int = Field(default=20_000, ge=100, le=200_000)
    CONVERSATION_SUMMARY_MAX_CHARS: int = Field(default=8_000, ge=100, le=100_000)
    CONVERSATION_RETENTION_DAYS: int = Field(default=30, ge=1, le=3650)
    CHAT_RETRIEVAL_TOP_K: int = Field(default=6, ge=1, le=20)
    CHAT_MIN_GROUNDED_SCORE: float = Field(default=0.02, ge=0.0, le=1.0)
    CHAT_MAX_OUTPUT_TOKENS: int = Field(default=800, ge=64, le=8000)
    WIDGET_SESSION_AUDIENCE: str = "support-agent-widget"
    WIDGET_SESSION_TTL_SECONDS: int = Field(default=900, ge=60, le=3600)
    WIDGET_SESSION_RATE_LIMIT: int = Field(default=20, ge=1, le=1000)
    WIDGET_SESSION_RATE_WINDOW_SECONDS: int = Field(default=60, ge=1, le=3600)
    WIDGET_MESSAGE_RATE_LIMIT: int = Field(default=30, ge=1, le=1000)
    WIDGET_MESSAGE_RATE_WINDOW_SECONDS: int = Field(default=60, ge=1, le=3600)

    # Ingestion queue. Work is always executed outside API request workers.
    INGESTION_QUEUE_NAME: str = "support-agent:ingestion"
    INGESTION_MAX_ATTEMPTS: int = Field(default=5, ge=1, le=20)
    INGESTION_RETRY_BASE_SECONDS: int = Field(default=5, ge=1, le=3600)
    INGESTION_RETRY_MAX_SECONDS: int = Field(default=300, ge=1, le=86400)
    INGESTION_JOB_TIMEOUT_SECONDS: int = Field(default=900, ge=30, le=86400)

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
        if self.INGESTION_RETRY_MAX_SECONDS < self.INGESTION_RETRY_BASE_SECONDS:
            raise ValueError(
                "INGESTION_RETRY_MAX_SECONDS must be greater than or equal to "
                "INGESTION_RETRY_BASE_SECONDS"
            )
        if self.CHUNK_OVERLAP_TOKENS >= self.CHUNK_MAX_TOKENS:
            raise ValueError("CHUNK_OVERLAP_TOKENS must be smaller than CHUNK_MAX_TOKENS")
        if self.AI_PROVIDER_MODE == "openai_compatible":
            if not self.AI_BASE_URL or self.AI_API_KEY is None:
                raise ValueError(
                    "AI_BASE_URL and AI_API_KEY are required for openai_compatible mode"
                )
            if not self.is_local and not self.AI_BASE_URL.startswith("https://"):
                raise ValueError("AI_BASE_URL must use HTTPS outside development and test")
        return self

    @property
    def is_local(self) -> bool:
        return self.APP_ENV in ("development", "test")

    @property
    def auth_jwt_secret(self) -> str:
        configured = self.AUTH_JWT_SECRET or _ephemeral_local_auth_secret
        return configured.get_secret_value()


settings = Settings()  # type: ignore[call-arg]
