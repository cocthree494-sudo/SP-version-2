"""Smoke tests for the migration environment and initial revision."""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_alembic_has_bot_revision_after_auth() -> None:
    api_root = Path(__file__).resolve().parents[1]
    config = Config(str(api_root / "alembic.ini"))
    scripts = ScriptDirectory.from_config(config)

    assert scripts.get_current_head() == "0004_bots"
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
