# Conversations, context, and retention

T-042 stores every conversation and message with an explicit `tenant_id`.
Messages use a per-conversation sequence allocated while the conversation row is
locked. Composite tenant foreign keys prevent a message from referencing a
conversation, or a conversation from referencing a bot, in another tenant.
PostgreSQL forces row-level security on both tables in addition to fail-closed
repository predicates.

The agent context consists of a server-generated rolling summary plus a bounded
window of recent verbatim turns. `RollingSummaryProvider` is provider-neutral:
compaction passes only the previous summary and newly compactable messages, then
advances `summary_through_sequence` atomically. Original messages remain stored
until the retention policy purges the conversation.

`retention_expires_at` is refreshed whenever a message is appended. A bounded,
tenant-scoped purge selects expired conversations with row locks and invokes a
`ConversationRetentionHook` before deletion so future cache, export, or external
storage cleanup can participate. The default hook performs no external work;
the database cascade removes messages.

Relevant settings are `CONVERSATION_RECENT_MESSAGE_LIMIT`,
`CONVERSATION_MESSAGE_MAX_CHARS`, `CONVERSATION_SUMMARY_MAX_CHARS`, and
`CONVERSATION_RETENTION_DAYS`.

