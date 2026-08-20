"""Add redacted user-to-workspace drill-down reporting views."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0021_admin_user_drilldown"
down_revision = "0020_platform_admin"
branch_labels = None
depends_on = None

_REPORTING_ROLE = "support_agent_reporting"
_VIEWS = (
    "platform_admin_user_tenants",
    "platform_admin_user_bots",
    "platform_admin_user_sources",
    "platform_admin_user_conversations",
)


def _create_view(name: str, sql: str) -> None:
    op.execute(sa.text(f"CREATE VIEW {name} AS {sql}"))
    op.execute(sa.text(f"GRANT SELECT ON {name} TO {_REPORTING_ROLE}"))


def upgrade() -> None:
    _create_view(
        "platform_admin_user_tenants",
        """
        SELECT tm.user_id, t.id AS tenant_id, t.name, t.slug, t.status::text AS status,
               tm.role::text AS role, tm.created_at AS joined_at,
               (SELECT COUNT(*) FROM tenant_memberships m2 WHERE m2.tenant_id = t.id)::int AS member_count,
               (SELECT COUNT(*) FROM bots b WHERE b.tenant_id = t.id)::int AS bot_count,
               (SELECT COUNT(*) FROM knowledge_sources ks WHERE ks.tenant_id = t.id)::int AS source_count,
               (SELECT COUNT(*) FROM conversations c WHERE c.tenant_id = t.id)::int AS conversation_count,
               (SELECT COALESCE(SUM(ue.input_tokens + ue.output_tokens), 0) FROM usage_events ue WHERE ue.tenant_id = t.id)::bigint AS token_count,
               (SELECT COALESCE(SUM(ue.estimated_cost_microusd), 0) FROM usage_events ue WHERE ue.tenant_id = t.id)::bigint AS estimated_cost_microusd,
               GREATEST(
                   COALESCE((SELECT MAX(ue.created_at) FROM usage_events ue WHERE ue.tenant_id = t.id), t.created_at),
                   COALESCE((SELECT MAX(b.created_at) FROM bots b WHERE b.tenant_id = t.id), t.created_at)
               ) AS last_activity_at
        FROM tenant_memberships tm JOIN tenants t ON t.id = tm.tenant_id
        """,
    )
    _create_view(
        "platform_admin_user_bots",
        """
        SELECT b.id AS bot_id, b.tenant_id, t.name AS tenant_name, b.name,
               b.status::text AS status, b.default_language, b.widget_welcome_text,
               b.widget_accent_color, b.widget_position,
               (b.system_policy IS NOT NULL AND length(b.system_policy) > 0) AS has_system_policy,
               LEFT(COALESCE(b.system_policy, ''), 1000) AS system_policy_preview,
               (SELECT COUNT(*) FROM bot_keys bk WHERE bk.bot_id = b.id AND bk.tenant_id = b.tenant_id)::int AS key_count,
               (SELECT COUNT(*) FROM bot_keys bk WHERE bk.bot_id = b.id AND bk.tenant_id = b.tenant_id AND bk.revoked_at IS NULL)::int AS active_key_count,
               (SELECT COUNT(*) FROM knowledge_sources ks WHERE ks.bot_id = b.id AND ks.tenant_id = b.tenant_id)::int AS source_count,
               (SELECT COUNT(*) FROM conversations c WHERE c.bot_id = b.id AND c.tenant_id = b.tenant_id)::int AS conversation_count,
               GREATEST(
                   b.created_at,
                   COALESCE((SELECT MAX(ue.created_at) FROM usage_events ue WHERE ue.bot_id = b.id AND ue.tenant_id = b.tenant_id), b.created_at)
               ) AS last_activity_at
        FROM bots b JOIN tenants t ON t.id = b.tenant_id
        """,
    )
    _create_view(
        "platform_admin_user_sources",
        """
        SELECT ks.id AS source_id, ks.tenant_id, t.name AS tenant_name, ks.bot_id,
               b.name AS bot_name, ks.type::text AS source_type, ks.name, ks.status::text AS status,
               CASE
                   WHEN ks.type::text = 'website' THEN jsonb_build_object(
                       'start_url', ks.configuration ->> 'start_url',
                       'max_pages', ks.configuration -> 'max_pages',
                       'max_depth', ks.configuration -> 'max_depth',
                       'request_delay_seconds', ks.configuration -> 'request_delay_seconds'
                   )
                   WHEN ks.type::text = 'file' THEN jsonb_build_object(
                       'original_filename', ks.configuration ->> 'original_filename',
                       'file_kind', ks.configuration ->> 'file_kind',
                       'media_type', ks.configuration ->> 'media_type',
                       'size_bytes', ks.configuration -> 'size_bytes',
                       'checksum_sha256', ks.configuration ->> 'checksum_sha256'
                   )
                   ELSE '{}'::jsonb
               END AS details,
               ks.error_code, LEFT(COALESCE(ks.error_message, ''), 500) AS error_message,
               (SELECT COUNT(*) FROM documents d WHERE d.source_id = ks.id AND d.tenant_id = ks.tenant_id)::int AS document_count,
               (SELECT COUNT(*) FROM documents d WHERE d.source_id = ks.id AND d.tenant_id = ks.tenant_id AND d.status::text = 'active')::int AS active_document_count,
               (SELECT COUNT(*) FROM document_chunks dc JOIN documents d ON d.id = dc.document_id AND d.tenant_id = dc.tenant_id WHERE d.source_id = ks.id AND d.tenant_id = ks.tenant_id)::int AS chunk_count,
               LEFT(CASE WHEN ks.type::text = 'manual' THEN COALESCE(ks.configuration ->> 'question', '') || E'\\n' || COALESCE(ks.configuration ->> 'answer', '') ELSE '' END, 1000) AS content_preview,
               ks.updated_at
        FROM knowledge_sources ks JOIN bots b ON b.id = ks.bot_id AND b.tenant_id = ks.tenant_id
        JOIN tenants t ON t.id = ks.tenant_id
        """,
    )
    _create_view(
        "platform_admin_user_conversations",
        """
        SELECT c.tenant_id, t.name AS tenant_name, c.bot_id, b.name AS bot_name, c.channel,
               COUNT(DISTINCT c.id)::int AS conversation_count,
               COUNT(m.id)::int AS message_count,
               MAX(c.updated_at) AS last_activity_at,
               COUNT(DISTINCT c.id) FILTER (WHERE c.status::text = 'active')::int AS active_count
        FROM conversations c JOIN tenants t ON t.id = c.tenant_id
        JOIN bots b ON b.id = c.bot_id AND b.tenant_id = c.tenant_id
        LEFT JOIN messages m ON m.conversation_id = c.id AND m.tenant_id = c.tenant_id
        GROUP BY c.tenant_id, t.name, c.bot_id, b.name, c.channel
        """,
    )


def downgrade() -> None:
    for view in reversed(_VIEWS):
        op.execute(sa.text(f"DROP VIEW IF EXISTS {view}"))
