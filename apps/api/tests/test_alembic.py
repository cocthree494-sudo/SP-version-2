"""Smoke tests for the migration environment and initial revision."""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import JSON, Column, String

from app.db.migrations import compare_server_default


def test_json_server_defaults_compare_without_database_equality() -> None:
    json_column = Column("payload", JSON())

    assert (
        compare_server_default(None, None, json_column, "('[]'::json)", None, "[]")
        is False
    )
    assert (
        compare_server_default(None, None, json_column, "'{}'::json", None, "[]")
        is True
    )
    assert (
        compare_server_default(
            None, None, Column("name", String()), "'same'", None, "'same'"
        )
        is None
    )


def test_alembic_has_conversation_revision_after_knowledge() -> None:
    api_root = Path(__file__).resolve().parents[1]
    config = Config(str(api_root / "alembic.ini"))
    scripts = ScriptDirectory.from_config(config)

    assert scripts.get_current_head() == "0011_widget_configuration"
    revision = scripts.get_revision("0002_tenancy")
    assert revision is not None
    assert revision.down_revision == "0001_enable_pgvector"
    pgvector_migration = api_root / "alembic" / "versions" / "0001_enable_pgvector.py"
    assert "CREATE EXTENSION IF NOT EXISTS vector" in pgvector_migration.read_text(encoding="utf-8")

    tenancy_migration = api_root / "alembic" / "versions" / "0002_tenancy.py"
    migration_text = tenancy_migration.read_text(encoding="utf-8")
    assert '"users"' in migration_text
    assert '"tenants"' in migration_text
    assert '"tenant_memberships"' in migration_text
    assert "ENABLE ROW LEVEL SECURITY" in migration_text
    assert "FORCE ROW LEVEL SECURITY" in migration_text
    assert "tenant_memberships_tenant_isolation" in migration_text

    auth_revision = scripts.get_revision("0003_auth")
    assert auth_revision is not None
    assert auth_revision.down_revision == "0002_tenancy"
    auth_migration = api_root / "alembic" / "versions" / "0003_auth.py"
    auth_migration_text = auth_migration.read_text(encoding="utf-8")
    assert '"refresh_tokens"' in auth_migration_text
    assert "refresh_tokens_tenant_isolation" in auth_migration_text
    assert "FORCE ROW LEVEL SECURITY" in auth_migration_text
    assert "tenant_memberships_authenticated_user_select" in auth_migration_text
    assert "app.user_id" in auth_migration_text

    bot_revision = scripts.get_revision("0004_bots")
    assert bot_revision is not None
    assert bot_revision.down_revision == "0003_auth"
    bot_migration = api_root / "alembic" / "versions" / "0004_bots.py"
    bot_migration_text = bot_migration.read_text(encoding="utf-8")
    assert '"bots"' in bot_migration_text
    assert '"bot_keys"' in bot_migration_text
    assert "bots_tenant_isolation" in bot_migration_text
    assert "bot_keys_tenant_isolation" in bot_migration_text

    usage_revision = scripts.get_revision("0005_usage")
    assert usage_revision is not None
    assert usage_revision.down_revision == "0004_bots"
    usage_migration = api_root / "alembic" / "versions" / "0005_usage.py"
    usage_migration_text = usage_migration.read_text(encoding="utf-8")
    assert '"usage_events"' in usage_migration_text
    assert "usage_events_tenant_isolation" in usage_migration_text
    assert "usage_events_prevent_mutation" in usage_migration_text

    knowledge_revision = scripts.get_revision("0006_knowledge_ingestion")
    assert knowledge_revision is not None
    assert knowledge_revision.down_revision == "0005_usage"
    knowledge_migration = (
        api_root / "alembic" / "versions" / "0006_knowledge_ingestion.py"
    )
    knowledge_migration_text = knowledge_migration.read_text(encoding="utf-8")
    assert '"knowledge_sources"' in knowledge_migration_text
    assert '"documents"' in knowledge_migration_text
    assert '"ingestion_jobs"' in knowledge_migration_text
    assert "knowledge_sources_tenant_isolation" in knowledge_migration_text
    assert "documents_tenant_isolation" in knowledge_migration_text
    assert "ingestion_jobs_tenant_isolation" in knowledge_migration_text

    chunk_revision = scripts.get_revision("0007_document_chunks")
    assert chunk_revision is not None
    assert chunk_revision.down_revision == "0006_knowledge_ingestion"
    chunk_migration = api_root / "alembic" / "versions" / "0007_document_chunks.py"
    chunk_migration_text = chunk_migration.read_text(encoding="utf-8")
    assert '"document_chunks"' in chunk_migration_text
    assert "search_vector" in chunk_migration_text
    assert "USING GIN" in chunk_migration_text
    assert "document_chunks_tenant_isolation" in chunk_migration_text

    conversation_revision = scripts.get_revision("0008_conversations")
    assert conversation_revision is not None
    assert conversation_revision.down_revision == "0007_document_chunks"
    conversation_migration = api_root / "alembic" / "versions" / "0008_conversations.py"
    conversation_migration_text = conversation_migration.read_text(encoding="utf-8")
    assert '"conversations"' in conversation_migration_text
    assert '"messages"' in conversation_migration_text
    assert "fk_messages_tenant_conversation_conversations" in conversation_migration_text
    assert "conversations_tenant_isolation" in conversation_migration_text
    assert "messages_tenant_isolation" in conversation_migration_text

    role_revision = scripts.get_revision("0009_app_runtime_role")
    assert role_revision is not None
    assert role_revision.down_revision == "0008_conversations"
    role_migration = api_root / "alembic" / "versions" / "0009_app_runtime_role.py"
    role_migration_text = role_migration.read_text(encoding="utf-8")
    assert "support_agent_app" in role_migration_text
    assert "NOBYPASSRLS" in role_migration_text
    assert "GRANT SELECT, INSERT, UPDATE, DELETE" in role_migration_text

    provider_revision = scripts.get_revision("0010_provider_access")
    assert provider_revision is not None
    assert provider_revision.down_revision == "0009_app_runtime_role"
    provider_migration = api_root / "alembic" / "versions" / "0010_provider_access.py"
    provider_migration_text = provider_migration.read_text(encoding="utf-8")
    assert '"provider_credentials"' in provider_migration_text
    assert '"provider_policies"' in provider_migration_text
    assert "provider_credentials_tenant_isolation" in provider_migration_text
    assert "provider_policies_tenant_isolation" in provider_migration_text
    assert "GRANT SELECT, INSERT, UPDATE, DELETE" in provider_migration_text

    widget_revision = scripts.get_revision("0011_widget_configuration")
    assert widget_revision is not None
    assert widget_revision.down_revision == "0010_provider_access"
    widget_migration = api_root / "alembic" / "versions" / "0011_widget_configuration.py"
    widget_migration_text = widget_migration.read_text(encoding="utf-8")
    assert '"widget_welcome_text"' in widget_migration_text
    assert '"widget_accent_color"' in widget_migration_text
    assert '"widget_position"' in widget_migration_text
