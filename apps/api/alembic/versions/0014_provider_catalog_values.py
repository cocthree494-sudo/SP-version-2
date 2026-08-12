"""Allow versioned Hermes catalog providers in tenant credentials.

Revision ID: 0014_provider_catalog_values
Revises: 0013_runtime_identity_grant
Create Date: 2026-08-13
"""

from __future__ import annotations

from alembic import op

revision: str = "0014_provider_catalog_values"
down_revision: str | None = "0013_runtime_identity_grant"
branch_labels: tuple[str, ...] | None = None
depends_on: str | None = None

_PROVIDERS = (
    "ai-gateway", "alibaba", "alibaba-coding-plan", "anthropic", "arcee", "actual",
    "azure-foundry", "bedrock", "copilot", "copilot-acp", "custom", "deepseek",
    "fireworks", "gmi", "gemini", "huggingface", "kilocode", "kimi", "kimi-cn",
    "lmstudio", "minimax", "minimax-cn", "minimax-oauth", "novita", "nvidia",
    "nous-portal", "openai", "openai-codex", "openrouter", "opencode-go", "opencode-zen",
    "ollama-cloud", "qwen-oauth", "stepfun", "tencent-tokenhub", "xai", "xai-oauth",
    "xiaomi", "vertex", "zai",
)


def _check_sql() -> str:
    values = ", ".join(f"'{value}'" for value in _PROVIDERS)
    return f"provider IN ({values})"


def upgrade() -> None:
    op.drop_constraint(
        "generation_provider",
        table_name="provider_credentials",
        type_="check",
    )
    op.create_check_constraint(
        "generation_provider",
        "provider_credentials",
        _check_sql(),
    )


def downgrade() -> None:
    op.drop_constraint(
        "generation_provider",
        table_name="provider_credentials",
        type_="check",
    )
    op.create_check_constraint(
        "generation_provider",
        "provider_credentials",
        "provider = 'openai'",
    )
