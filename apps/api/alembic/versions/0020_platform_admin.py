"""Add the audited platform-admin control plane and redacted reporting views."""

# View/role identifiers below are module constants, never request input.
# ruff: noqa: E501, S608

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0020_platform_admin"
down_revision = "0019_user_email_verification"
branch_labels = None
depends_on = None

_APP_ROLE = "support_agent_app"
_REPORTING_ROLE = "support_agent_reporting"
_VIEWS = (
    "platform_admin_user_directory",
    "platform_admin_tenant_directory",
    "platform_admin_usage_events",
    "platform_admin_ingestion_jobs",
    "platform_admin_channel_health",
    "platform_admin_voice_health",
    "platform_admin_provider_health",
    "platform_admin_session_health",
    "platform_admin_audit_log",
)


def _create_reporting_role() -> None:
    op.execute(
        sa.text(
            f"""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{_REPORTING_ROLE}') THEN
                    CREATE ROLE {_REPORTING_ROLE}
                        LOGIN INHERIT
                        NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
                ELSE
                    ALTER ROLE {_REPORTING_ROLE}
                        LOGIN INHERIT
                        NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
                END IF;
            END
            $$
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            DO $$
            BEGIN
                EXECUTE format('GRANT CONNECT ON DATABASE %I TO { _REPORTING_ROLE }', current_database());
            END
            $$
            """.replace("{ _REPORTING_ROLE }", _REPORTING_ROLE)
        )
    )
    op.execute(sa.text(f"GRANT USAGE ON SCHEMA public TO {_REPORTING_ROLE}"))
    op.execute(sa.text(f"REVOKE CREATE ON SCHEMA public FROM {_REPORTING_ROLE}"))


def _create_view(name: str, sql: str) -> None:
    op.execute(sa.text(f"CREATE VIEW {name} AS {sql}"))
    op.execute(sa.text(f"GRANT SELECT ON {name} TO {_REPORTING_ROLE}"))


def upgrade() -> None:
    op.create_table(
        "platform_admins",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="active", nullable=False),
        sa.Column("granted_by_user_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("granted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('active', 'revoked')", name="ck_platform_admin_status"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_platform_admins_user_id"),
    )
    op.create_index("ix_platform_admins_user_id", "platform_admins", ["user_id"])
    op.create_index("ix_platform_admins_granted_by_user_id", "platform_admins", ["granted_by_user_id"])
    op.create_table(
        "platform_admin_audit_logs",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(length=120), nullable=False),
        sa.Column("target_type", sa.String(length=64), nullable=False),
        sa.Column("target_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("change_summary", sa.JSON(), server_default="{}", nullable=False),
        sa.CheckConstraint("length(action) BETWEEN 1 AND 120", name="ck_admin_audit_action"),
        sa.CheckConstraint("length(outcome) BETWEEN 1 AND 32", name="ck_admin_audit_outcome"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_platform_admin_audit_logs_actor_user_id", "platform_admin_audit_logs", ["actor_user_id"])
    op.create_index("ix_platform_admin_audit_logs_action", "platform_admin_audit_logs", ["action"])
    op.create_index("ix_platform_admin_audit_logs_target_id", "platform_admin_audit_logs", ["target_id"])
    op.create_index("ix_platform_admin_audit_logs_request_id", "platform_admin_audit_logs", ["request_id"])
    op.execute(sa.text(f"GRANT SELECT, INSERT ON platform_admins, platform_admin_audit_logs TO {_APP_ROLE}"))

    op.execute(
        sa.text(
            """
            CREATE FUNCTION prevent_platform_admin_audit_mutation()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                RAISE EXCEPTION 'platform admin audit records are immutable';
            END;
            $$
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TRIGGER platform_admin_audit_immutable
            BEFORE UPDATE OR DELETE ON platform_admin_audit_logs
            FOR EACH ROW EXECUTE FUNCTION prevent_platform_admin_audit_mutation()
            """
        )
    )

    _create_reporting_role()
    _create_view(
        "platform_admin_user_directory",
        """
        SELECT u.id AS user_id, u.email, u.display_name, u.status::text AS status,
               u.email_verified_at, u.created_at,
               COUNT(DISTINCT tm.tenant_id)::int AS tenant_count,
               MAX(rt.created_at) AS last_session_at,
               COUNT(rt.id) FILTER (WHERE rt.revoked_at IS NULL AND rt.expires_at > now())::int AS active_session_count
        FROM users u
        LEFT JOIN tenant_memberships tm ON tm.user_id = u.id
        LEFT JOIN refresh_tokens rt ON rt.user_id = u.id
        GROUP BY u.id
        """,
    )
    _create_view(
        "platform_admin_tenant_directory",
        """
        SELECT t.id AS tenant_id, t.name, t.slug, t.status::text AS status, t.created_at,
               (SELECT COUNT(*) FROM tenant_memberships tm WHERE tm.tenant_id = t.id)::int AS member_count,
               (SELECT COUNT(*) FROM bots b WHERE b.tenant_id = t.id)::int AS bot_count,
               (SELECT COUNT(*) FROM knowledge_sources ks WHERE ks.tenant_id = t.id)::int AS source_count,
               (SELECT COUNT(*) FROM conversations c WHERE c.tenant_id = t.id)::int AS conversation_count,
               (SELECT COALESCE(SUM(ue.input_tokens + ue.output_tokens), 0) FROM usage_events ue WHERE ue.tenant_id = t.id)::bigint AS token_count,
               (SELECT COALESCE(SUM(ue.estimated_cost_microusd), 0) FROM usage_events ue WHERE ue.tenant_id = t.id)::bigint AS estimated_cost_microusd,
               GREATEST(
                   COALESCE((SELECT MAX(ue.created_at) FROM usage_events ue WHERE ue.tenant_id = t.id), t.created_at),
                   COALESCE((SELECT MAX(b.created_at) FROM bots b WHERE b.tenant_id = t.id), t.created_at)
               ) AS last_activity_at
        FROM tenants t
        """,
    )
    _create_view(
        "platform_admin_usage_events",
        """
        SELECT ue.id AS usage_event_id, ue.tenant_id, t.name AS tenant_name, t.slug AS tenant_slug,
               ue.bot_id, ue.operation::text AS operation, ue.provider, ue.model,
               ue.input_tokens, ue.output_tokens, ue.cache_read_tokens, ue.cache_write_tokens,
               ue.latency_ms, ue.estimated_cost_microusd, ue.created_at
        FROM usage_events ue JOIN tenants t ON t.id = ue.tenant_id
        """,
    )
    _create_view(
        "platform_admin_ingestion_jobs",
        """
        SELECT ij.id AS job_id, ij.tenant_id, t.name AS tenant_name, ij.source_id,
               ks.name AS source_name, ij.type::text AS job_type, ij.state::text AS state,
               ij.attempts, ij.max_attempts, ij.progress_percent, ij.scheduled_at,
               ij.started_at, ij.completed_at, ij.error_code,
               LEFT(COALESCE(ij.error_message, ''), 500) AS error_message, ij.created_at
        FROM ingestion_jobs ij
        JOIN tenants t ON t.id = ij.tenant_id
        LEFT JOIN knowledge_sources ks ON ks.id = ij.source_id AND ks.tenant_id = ij.tenant_id
        """,
    )
    _create_view(
        "platform_admin_channel_health",
        """
        SELECT ci.id AS installation_id, ci.tenant_id, t.name AS tenant_name,
               ci.channel_type::text AS channel_type, ci.status::text AS status,
               CASE
                   WHEN ci.external_identity IS NULL THEN NULL
                   WHEN length(ci.external_identity) > 4
                       THEN left(ci.external_identity, 2) || '...' || right(ci.external_identity, 2)
                   ELSE '***'
               END AS masked_external_identity,
               ci.expires_at, ci.created_at, ci.updated_at
        FROM channel_installations ci JOIN tenants t ON t.id = ci.tenant_id
        """,
    )
    _create_view(
        "platform_admin_voice_health",
        """
        SELECT vai.id AS installation_id, vai.tenant_id, t.name AS tenant_name,
               vai.provider,
               CASE
                   WHEN vai.phone_number IS NULL THEN NULL
                   WHEN length(vai.phone_number) > 4 THEN '***' || right(vai.phone_number, 4)
                   ELSE '***'
               END AS masked_phone_number,
               vai.status::text AS status,
               vai.outbound_enabled, vai.recording_enabled, vai.monthly_cost_limit_usd,
               vai.created_at, vai.updated_at
        FROM voice_agent_installations vai JOIN tenants t ON t.id = vai.tenant_id
        """,
    )
    _create_view(
        "platform_admin_provider_health",
        """
        SELECT pc.id AS credential_id, pc.tenant_id, t.name AS tenant_name,
               pc.provider::text AS provider, pc.label, pc.masked_secret,
               pc.low_cost_model_id, pc.strong_model_id, pc.status::text AS status,
               pc.verified_at, pc.rotated_at, pc.revoked_at, pc.created_at,
               pp.mode::text AS routing_mode
        FROM provider_credentials pc
        JOIN tenants t ON t.id = pc.tenant_id
        LEFT JOIN provider_policies pp ON pp.tenant_id = pc.tenant_id
        """,
    )
    _create_view(
        "platform_admin_session_health",
        """
        SELECT rt.id AS session_id, rt.user_id, u.email, rt.tenant_id, t.name AS tenant_name,
               rt.created_at, rt.expires_at, rt.revoked_at
        FROM refresh_tokens rt JOIN users u ON u.id = rt.user_id
        JOIN tenants t ON t.id = rt.tenant_id
        """,
    )
    _create_view(
        "platform_admin_audit_log",
        """
        SELECT id, created_at, actor_user_id, action, target_type, target_id, reason,
               outcome, request_id, ip_address, user_agent, change_summary
        FROM platform_admin_audit_logs
        """,
    )


def downgrade() -> None:
    for view in reversed(_VIEWS):
        op.execute(sa.text(f"DROP VIEW IF EXISTS {view}"))
    op.execute(sa.text(f"REVOKE USAGE ON SCHEMA public FROM {_REPORTING_ROLE}"))
    op.execute(sa.text(f"REVOKE CREATE ON SCHEMA public FROM {_REPORTING_ROLE}"))
    op.execute(sa.text(f"REVOKE SELECT ON ALL TABLES IN SCHEMA public FROM {_REPORTING_ROLE}"))
    op.execute(sa.text("DROP TRIGGER IF EXISTS platform_admin_audit_immutable ON platform_admin_audit_logs"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS prevent_platform_admin_audit_mutation()"))
    op.execute(sa.text(f"REVOKE SELECT, INSERT ON platform_admins, platform_admin_audit_logs FROM {_APP_ROLE}"))
    op.drop_index("ix_platform_admin_audit_logs_request_id", table_name="platform_admin_audit_logs")
    op.drop_index("ix_platform_admin_audit_logs_target_id", table_name="platform_admin_audit_logs")
    op.drop_index("ix_platform_admin_audit_logs_action", table_name="platform_admin_audit_logs")
    op.drop_index("ix_platform_admin_audit_logs_actor_user_id", table_name="platform_admin_audit_logs")
    op.drop_table("platform_admin_audit_logs")
    op.drop_index("ix_platform_admins_granted_by_user_id", table_name="platform_admins")
    op.drop_index("ix_platform_admins_user_id", table_name="platform_admins")
    op.drop_table("platform_admins")
