"""Raw SQL proofs for every PostgreSQL tenant policy and the usage trigger."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.db.base import Base, utc_now
from app.domains.auth import models as _auth_models  # noqa: F401
from app.domains.bots import models as _bot_models  # noqa: F401
from app.domains.channels import models as _channel_models  # noqa: F401
from app.domains.chat import models as _chat_models  # noqa: F401
from app.domains.knowledge import models as _knowledge_models  # noqa: F401
from app.domains.provider_access import models as _provider_access_models  # noqa: F401
from app.domains.tenancy import models as _tenancy_models  # noqa: F401
from app.domains.usage import models as _usage_models  # noqa: F401
from app.domains.voice import models as _voice_models  # noqa: F401

TENANT_TABLES = (
    "tenant_memberships",
    "refresh_tokens",
    "bots",
    "bot_keys",
    "usage_events",
    "knowledge_sources",
    "documents",
    "ingestion_jobs",
    "document_chunks",
    "conversations",
    "messages",
    "provider_credentials",
    "provider_policies",
    "channel_installations",
    "voice_agent_installations",
    "voice_webhook_events",
)


def test_rls_matrix_covers_every_tenant_owned_model() -> None:
    model_tables = {
        table.name
        for table in Base.metadata.sorted_tables
        if "tenant_id" in table.columns and not table.name.startswith("test_")
    }
    assert set(TENANT_TABLES) == model_tables


@dataclass(frozen=True, slots=True)
class SeedRows:
    tenant_a: UUID
    tenant_b: UUID
    row_ids: dict[str, UUID]
    insert_user_id: UUID
    insert_document_id: UUID


def _insert_sql(table: str, row_id: UUID, seed: SeedRows) -> tuple[str, dict[str, object]]:
    """Build a valid tenant-B row that must still fail tenant-A RLS WITH CHECK."""

    tenant_id = seed.tenant_b
    params: dict[str, object] = {"id": row_id, "tenant_id": tenant_id}
    if table == "tenant_memberships":
        params["user_id"] = seed.insert_user_id
        return (
            "INSERT INTO tenant_memberships (id, tenant_id, user_id, role) "
            "VALUES (:id, :tenant_id, :user_id, 'member')",
            params,
        )
    if table == "refresh_tokens":
        params.update(
            user_id=seed.insert_user_id,
            family_id=uuid4(),
            token_hash="c" * 64,
        )
        return (
            "INSERT INTO refresh_tokens "
            "(id, user_id, tenant_id, family_id, token_hash, expires_at) "
            "VALUES (:id, :user_id, :tenant_id, :family_id, :token_hash, now() + interval '1 day')",
            params,
        )
    if table == "bots":
        params.update(name="Cross-tenant insert", default_language="auto", status="active")
        return (
            "INSERT INTO bots (id, tenant_id, name, default_language, status) "
            "VALUES (:id, :tenant_id, :name, :default_language, :status)",
            params,
        )
    if table == "bot_keys":
        params.update(
            bot_id=seed.row_ids["bots"],
            publishable_key="c" * 80,
            label="Cross-tenant insert",
            allowed_origins="[]",
        )
        return (
            "INSERT INTO bot_keys "
            "(id, tenant_id, bot_id, publishable_key, label, allowed_origins) "
            "VALUES (:id, :tenant_id, :bot_id, :publishable_key, :label, "
            "CAST(:allowed_origins AS json))",
            params,
        )
    if table == "usage_events":
        params.update(operation="generation", provider="test", model="test-model")
        return (
            "INSERT INTO usage_events "
            "(id, tenant_id, operation, provider, model) "
            "VALUES (:id, :tenant_id, :operation, :provider, :model)",
            params,
        )
    if table == "knowledge_sources":
        params.update(bot_id=seed.row_ids["bots"], type="manual", name="Cross-tenant insert")
        return (
            "INSERT INTO knowledge_sources "
            "(id, tenant_id, bot_id, type, name, configuration) "
            "VALUES (:id, :tenant_id, :bot_id, :type, :name, CAST('{}' AS json))",
            params,
        )
    if table == "documents":
        params.update(
            source_id=seed.row_ids["knowledge_sources"],
            document_key="cross-insert",
            version=99,
            checksum_sha256="c" * 64,
            title="Cross-tenant insert",
            status="staged",
        )
        return (
            "INSERT INTO documents "
            "(id, tenant_id, source_id, document_key, version, checksum_sha256, "
            "title, metadata, status) "
            "VALUES (:id, :tenant_id, :source_id, :document_key, :version, :checksum_sha256, "
            ":title, CAST('{}' AS json), :status)",
            params,
        )
    if table == "ingestion_jobs":
        params.update(
            source_id=seed.row_ids["knowledge_sources"],
            type="ingest_source",
            state="queued",
            idempotency_key=f"cross-{row_id}",
            max_attempts=3,
        )
        return (
            "INSERT INTO ingestion_jobs "
            "(id, tenant_id, source_id, type, state, idempotency_key, max_attempts, payload) "
            "VALUES (:id, :tenant_id, :source_id, :type, :state, :idempotency_key, "
            ":max_attempts, CAST('{}' AS json))",
            params,
        )
    if table == "document_chunks":
        params.update(
            document_id=seed.insert_document_id,
            ordinal=1,
            content="Cross-tenant insert",
            content_checksum_sha256="d" * 64,
            token_count=2,
            start_char=0,
            end_char=19,
            embedding="[0.1,0.2,0.3]",
            embedding_provider="test",
            embedding_model="test-model",
        )
        return (
            "INSERT INTO document_chunks "
            "(id, tenant_id, document_id, ordinal, content, content_checksum_sha256, token_count, "
            "start_char, end_char, embedding, embedding_provider, embedding_model, metadata) "
            "VALUES (:id, :tenant_id, :document_id, :ordinal, :content, :content_checksum_sha256, "
            ":token_count, :start_char, :end_char, CAST(:embedding AS vector), "
            ":embedding_provider, "
            ":embedding_model, CAST('{}' AS json))",
            params,
        )
    if table == "conversations":
        params.update(
            bot_id=seed.row_ids["bots"],
            channel="test",
            retention_expires_at=utc_now() + timedelta(days=1),
        )
        return (
            "INSERT INTO conversations "
            "(id, tenant_id, bot_id, channel, status, summary_through_sequence, "
            "next_message_sequence, retention_expires_at) "
            "VALUES (:id, :tenant_id, :bot_id, :channel, 'active', 0, 1, :retention_expires_at)",
            params,
        )
    if table == "messages":
        params.update(
            conversation_id=seed.row_ids["conversations"],
            sequence=2,
            role="user",
            content="Cross-tenant insert",
        )
        return (
            "INSERT INTO messages "
            "(id, tenant_id, conversation_id, sequence, role, content, citations, metadata) "
            "VALUES (:id, :tenant_id, :conversation_id, :sequence, :role, :content, "
            "CAST('[]' AS json), CAST('{}' AS json))",
            params,
        )
    if table == "provider_credentials":
        params.update(
            provider="openai",
            label="Cross-tenant credential",
            encrypted_secret="cross-ciphertext",  # noqa: S106 - non-secret fixture value
            wrapped_data_key="cross-wrapped-key",
            key_version="test-v1",
            masked_secret="••••ross",  # noqa: S106 - non-secret fixture value
            fingerprint="c" * 64,
            low_cost_model_id="test-low",
        )
        return (
            "INSERT INTO provider_credentials "
            "(id, tenant_id, provider, label, encrypted_secret, wrapped_data_key, "
            "key_version, masked_secret, fingerprint, low_cost_model_id) "
            "VALUES (:id, :tenant_id, :provider, :label, :encrypted_secret, "
            ":wrapped_data_key, :key_version, :masked_secret, :fingerprint, "
            ":low_cost_model_id)",
            params,
        )
    if table == "provider_policies":
        params.update(mode="platform_only", credential_order="[]")
        return (
            "INSERT INTO provider_policies (id, tenant_id, mode, credential_order) "
            "VALUES (:id, :tenant_id, :mode, CAST(:credential_order AS json))",
            params,
        )
    if table == "channel_installations":
        params.update(
            channel_type="email",
            external_identity="cross@example.test",
            status="pending",
            conversation_scope="[]",
            consent_record='{"acknowledged": true}',
        )
        return (
            "INSERT INTO channel_installations "
            "(id, tenant_id, channel_type, external_identity, status, "
            "conversation_scope, consent_record) "
            "VALUES (:id, :tenant_id, :channel_type, :external_identity, :status, "
            "CAST(:conversation_scope AS json), CAST(:consent_record AS json))",
            params,
        )
    if table == "voice_agent_installations":
        params.update(phone_number=f"+1555{str(row_id.int)[-7:]}")
        return (
            "INSERT INTO voice_agent_installations "
            "(id, tenant_id, phone_number, provider, language, voice, business_hours, "
            "outbound_enabled, recording_enabled, retention_days, monthly_cost_limit_usd, status) "
            "VALUES (:id, :tenant_id, :phone_number, 'twilio', 'auto', 'alloy', "
            "CAST('{}' AS json), "
            "false, false, 0, 100, 'pending')",
            params,
        )
    if table == "voice_webhook_events":
        params.update(
            installation_id=seed.row_ids["voice_agent_installations"],
            event_id=f"cross-{row_id}",
            event_type="call.started",
            payload="{}",
        )
        return (
            "INSERT INTO voice_webhook_events "
            "(id, tenant_id, installation_id, event_id, event_type, payload) "
            "VALUES (:id, :tenant_id, :installation_id, :event_id, :event_type, "
            "CAST(:payload AS json))",
            params,
        )
    raise AssertionError(f"Missing RLS insert fixture for {table}")


@pytest_asyncio.fixture
async def seeded_rows(admin_postgres_engine: AsyncEngine) -> AsyncIterator[SeedRows]:
    """Commit one tenant-B graph through the owner connection for raw RLS probes."""

    tenant_a = uuid4()
    tenant_b = uuid4()
    user_b = uuid4()
    insert_user = uuid4()
    row_ids = {table: uuid4() for table in TENANT_TABLES}
    insert_document_id = uuid4()
    seed = SeedRows(tenant_a, tenant_b, row_ids, insert_user, insert_document_id)
    async with admin_postgres_engine.begin() as connection:
        await connection.execute(text("TRUNCATE users, tenants CASCADE"))
        await connection.execute(
            text(
                "INSERT INTO users (id, email, password_hash, status) VALUES "
                "(:user_b, :email_b, :password, 'active'), "
                "(:insert_user, :email_insert, :password, 'active')"
            ),
            {
                "user_b": user_b,
                "email_b": f"rls-b-{user_b}@example.test",
                "insert_user": insert_user,
                "email_insert": f"rls-insert-{insert_user}@example.test",
                "password": "not-used",
            },
        )
        await connection.execute(
            text(
                "INSERT INTO tenants (id, name, slug, status, settings) VALUES "
                "(:tenant_a, 'RLS A', :slug_a, 'active', CAST('{}' AS json)), "
                "(:tenant_b, 'RLS B', :slug_b, 'active', CAST('{}' AS json))"
            ),
            {
                "tenant_a": tenant_a,
                "slug_a": f"rls-a-{tenant_a}",
                "tenant_b": tenant_b,
                "slug_b": f"rls-b-{tenant_b}",
            },
        )
        await connection.execute(
            text(
                "INSERT INTO tenant_memberships (id, tenant_id, user_id, role) "
                "VALUES (:id, :tenant_b, :user_b, 'member')"
            ),
            {"id": row_ids["tenant_memberships"], "tenant_b": tenant_b, "user_b": user_b},
        )
        await connection.execute(
            text(
                "INSERT INTO refresh_tokens "
                "(id, user_id, tenant_id, family_id, token_hash, expires_at) "
                "VALUES (:id, :user_b, :tenant_b, :family, :hash, now() + interval '1 day')"
            ),
            {
                "id": row_ids["refresh_tokens"],
                "user_b": user_b,
                "tenant_b": tenant_b,
                "family": uuid4(),
                "hash": "b" * 64,
            },
        )
        await connection.execute(
            text(
                "INSERT INTO bots (id, tenant_id, name, default_language, status) "
                "VALUES (:id, :tenant_b, 'RLS Bot', 'auto', 'active')"
            ),
            {"id": row_ids["bots"], "tenant_b": tenant_b},
        )
        await connection.execute(
            text(
                "INSERT INTO bot_keys "
                "(id, tenant_id, bot_id, publishable_key, label, allowed_origins) "
                "VALUES (:id, :tenant_b, :bot, :key, 'RLS key', CAST('[]' AS json))"
            ),
            {
                "id": row_ids["bot_keys"],
                "tenant_b": tenant_b,
                "bot": row_ids["bots"],
                "key": "b" * 80,
            },
        )
        await connection.execute(
            text(
                "INSERT INTO usage_events (id, tenant_id, operation, provider, model) "
                "VALUES (:id, :tenant_b, 'generation', 'test', 'test-model')"
            ),
            {"id": row_ids["usage_events"], "tenant_b": tenant_b},
        )
        await connection.execute(
            text(
                "INSERT INTO knowledge_sources "
                "(id, tenant_id, bot_id, type, name, status, configuration) "
                "VALUES (:id, :tenant_b, :bot, 'manual', 'RLS source', 'ready', CAST('{}' AS json))"
            ),
            {
                "id": row_ids["knowledge_sources"],
                "tenant_b": tenant_b,
                "bot": row_ids["bots"],
            },
        )
        await connection.execute(
            text(
                "INSERT INTO channel_installations "
                "(id, tenant_id, channel_type, external_identity, status, "
                "conversation_scope, consent_record) "
                "VALUES (:id, :tenant_b, 'email', 'rls-b@example.test', 'pending', "
                "CAST('[]' AS json), CAST('{\"acknowledged\": true}' AS json))"
            ),
            {"id": row_ids["channel_installations"], "tenant_b": tenant_b},
        )
        await connection.execute(
            text(
                "INSERT INTO voice_agent_installations "
                "(id, tenant_id, phone_number, provider, language, voice, business_hours, "
                "outbound_enabled, recording_enabled, retention_days, "
                "monthly_cost_limit_usd, status) "
                "VALUES (:id, :tenant_b, '+15550199', 'twilio', 'auto', 'alloy', "
                "CAST('{}' AS json), "
                "false, false, 0, 100, 'pending')"
            ),
            {"id": row_ids["voice_agent_installations"], "tenant_b": tenant_b},
        )
        await connection.execute(
            text(
                "INSERT INTO voice_webhook_events "
                "(id, tenant_id, installation_id, event_id, event_type, payload) "
                "VALUES (:id, :tenant_b, :installation, 'rls-event', 'call.started', "
                "CAST('{}' AS json))"
            ),
            {
                "id": row_ids["voice_webhook_events"],
                "tenant_b": tenant_b,
                "installation": row_ids["voice_agent_installations"],
            },
        )
        await connection.execute(
            text(
                "INSERT INTO documents "
                "(id, tenant_id, source_id, document_key, version, checksum_sha256, "
                "title, metadata, status) "
                "VALUES (:id, :tenant_b, :source, 'primary', 1, :checksum, 'RLS document', "
                "CAST('{}' AS json), 'active')"
            ),
            {
                "id": row_ids["documents"],
                "tenant_b": tenant_b,
                "source": row_ids["knowledge_sources"],
                "checksum": "a" * 64,
            },
        )
        await connection.execute(
            text(
                "INSERT INTO ingestion_jobs "
                "(id, tenant_id, source_id, type, state, idempotency_key, max_attempts, payload) "
                "VALUES (:id, :tenant_b, :source, 'ingest_source', 'queued', :key, 3, "
                "CAST('{}' AS json))"
            ),
            {
                "id": row_ids["ingestion_jobs"],
                "tenant_b": tenant_b,
                "source": row_ids["knowledge_sources"],
                "key": f"rls-{row_ids['ingestion_jobs']}",
            },
        )
        await connection.execute(
            text(
                "INSERT INTO document_chunks "
                "(id, tenant_id, document_id, ordinal, content, content_checksum_sha256, "
                "token_count, "
                "start_char, end_char, embedding, embedding_provider, embedding_model, metadata) "
                "VALUES (:id, :tenant_b, :document, 0, 'Private tenant B content', :checksum, "
                "4, 0, 23, "
                "CAST('[0.1,0.2,0.3]' AS vector), 'test', 'test-model', CAST('{}' AS json))"
            ),
            {
                "id": row_ids["document_chunks"],
                "tenant_b": tenant_b,
                "document": row_ids["documents"],
                "checksum": "b" * 64,
            },
        )
        await connection.execute(
            text(
                "INSERT INTO conversations "
                "(id, tenant_id, bot_id, channel, status, retention_expires_at) "
                "VALUES (:id, :tenant_b, :bot, 'test', 'active', now() + interval '1 day')"
            ),
            {
                "id": row_ids["conversations"],
                "tenant_b": tenant_b,
                "bot": row_ids["bots"],
            },
        )
        await connection.execute(
            text(
                "INSERT INTO messages "
                "(id, tenant_id, conversation_id, sequence, role, content, citations, metadata) "
                "VALUES (:id, :tenant_b, :conversation, 1, 'user', 'Private tenant B message', "
                "CAST('[]' AS json), CAST('{}' AS json))"
            ),
            {
                "id": row_ids["messages"],
                "tenant_b": tenant_b,
                "conversation": row_ids["conversations"],
            },
        )
        await connection.execute(
            text(
                "INSERT INTO provider_credentials "
                "(id, tenant_id, provider, label, encrypted_secret, wrapped_data_key, "
                "key_version, masked_secret, fingerprint, low_cost_model_id, status) "
                "VALUES (:id, :tenant_b, 'openai', 'RLS credential', 'ciphertext', "
                "'wrapped-key', 'test-v1', '••••test', :fingerprint, "
                "'test-low', 'verified')"
            ),
            {
                "id": row_ids["provider_credentials"],
                "tenant_b": tenant_b,
                "fingerprint": "b" * 64,
            },
        )
        await connection.execute(
            text(
                "INSERT INTO provider_policies (id, tenant_id, mode, credential_order) "
                "VALUES (:id, :tenant_b, 'tenant_only', CAST(:credential_order AS json))"
            ),
            {
                "id": row_ids["provider_policies"],
                "tenant_b": tenant_b,
                "credential_order": f'["{row_ids["provider_credentials"]}"]',
            },
        )
        await connection.execute(
            text(
                "INSERT INTO documents "
                "(id, tenant_id, source_id, document_key, version, checksum_sha256, "
                "title, metadata, status) "
                "VALUES (:id, :tenant_b, :source, 'insert-document', 1, :checksum, "
                "'Insert document', "
                "CAST('{}' AS json), 'staged')"
            ),
            {
                "id": insert_document_id,
                "tenant_b": tenant_b,
                "source": row_ids["knowledge_sources"],
                "checksum": "e" * 64,
            },
        )
    try:
        yield seed
    finally:
        async with admin_postgres_engine.begin() as connection:
            await connection.execute(text("TRUNCATE users, tenants CASCADE"))


@pytest_asyncio.fixture
async def rls_session(
    postgres_engine: AsyncEngine,
    seeded_rows: SeedRows,
) -> AsyncIterator[AsyncSession]:
    """Ensure the restricted transaction closes before admin cleanup truncates."""

    del seeded_rows
    factory = async_sessionmaker(postgres_engine, expire_on_commit=False)
    async with factory() as session:
        try:
            yield session
        finally:
            await session.rollback()


async def _set_tenant(session: AsyncSession, tenant_id: UUID | None) -> None:
    value = "" if tenant_id is None else str(tenant_id)
    await session.execute(
        text("SELECT set_config('app.tenant_id', :value, true)"),
        {"value": value},
    )
    await session.execute(text("SELECT set_config('app.user_id', '', true)"))


def _assert_rls_violation(error: DBAPIError) -> None:
    sqlstate = getattr(error.orig, "sqlstate", None) or getattr(error.orig, "pgcode", None)
    assert sqlstate == "42501"
    assert "row-level security" in str(error).casefold()


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize("table", TENANT_TABLES)
async def test_rls_hides_and_rejects_cross_tenant_data(
    rls_session: AsyncSession,
    seeded_rows: SeedRows,
    table: str,
) -> None:
    await _set_tenant(rls_session, seeded_rows.tenant_a)
    row_id = seeded_rows.row_ids[table]

    visible = await rls_session.execute(
        text(f"SELECT id FROM {table} WHERE id = :id"),  # noqa: S608 - table is a fixed test constant
        {"id": row_id},
    )
    assert visible.all() == []

    updated = cast(
        CursorResult[Any],
        await rls_session.execute(
            text(f"UPDATE {table} SET id = id WHERE id = :id"),  # noqa: S608
            {"id": row_id},
        ),
    )
    assert updated.rowcount == 0
    deleted = cast(
        CursorResult[Any],
        await rls_session.execute(
            text(f"DELETE FROM {table} WHERE id = :id"),  # noqa: S608
            {"id": row_id},
        ),
    )
    assert deleted.rowcount == 0

    insert_id = uuid4()
    insert_query, insert_params = _insert_sql(table, insert_id, seeded_rows)
    with pytest.raises(DBAPIError) as cross_tenant_insert:
        async with rls_session.begin_nested():
            await rls_session.execute(text(insert_query), insert_params)
    _assert_rls_violation(cross_tenant_insert.value)

    await _set_tenant(rls_session, None)
    no_context = await rls_session.execute(
        text(f"SELECT id FROM {table}"),  # noqa: S608
    )
    assert no_context.all() == []
    no_context_query, no_context_params = _insert_sql(table, uuid4(), seeded_rows)
    with pytest.raises(DBAPIError) as missing_context_insert:
        async with rls_session.begin_nested():
            await rls_session.execute(text(no_context_query), no_context_params)
    _assert_rls_violation(missing_context_insert.value)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_usage_events_database_trigger_is_append_only(
    rls_session: AsyncSession,
    seeded_rows: SeedRows,
) -> None:
    await _set_tenant(rls_session, seeded_rows.tenant_b)
    usage_id = seeded_rows.row_ids["usage_events"]
    with pytest.raises(DBAPIError, match="usage_events is append-only") as update_error:
        async with rls_session.begin_nested():
            await rls_session.execute(
                text("UPDATE usage_events SET provider = 'mutated' WHERE id = :id"),
                {"id": usage_id},
            )
    assert getattr(update_error.value.orig, "sqlstate", None) == "55000"
    with pytest.raises(DBAPIError, match="usage_events is append-only") as delete_error:
        async with rls_session.begin_nested():
            await rls_session.execute(
                text("DELETE FROM usage_events WHERE id = :id"),
                {"id": usage_id},
            )
    assert getattr(delete_error.value.orig, "sqlstate", None) == "55000"
