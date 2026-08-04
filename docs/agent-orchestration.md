# Grounded support-agent orchestration

T-043 implements a channel-neutral `GroundedAnswerOrchestrator`. A turn loads
the tenant-bound conversation summary and recent window, retrieves only the
bot's active knowledge, and sends a small evidence set through the model router.

Trusted system and tenant policy are kept in a system message. Retrieved chunks
and rolling summaries are serialized as untrusted tool data. The system policy
explicitly forbids following commands, role changes, or secret requests found
inside knowledge. The customer's latest message stays in a user role.

Answers must cite one or more valid evidence ordinals such as `[1]`. An empty,
uncited, or out-of-range draft receives one observable strong-tier validation
retry. If retrieval is absent/weak or the retry still fails, the agent returns a
localized uncertainty message with no citations instead of inventing an answer.

The final user message, assistant message/citations/routing metadata, and every
provider usage event (including an invalid first draft) are flushed and committed
as one transaction. Any persistence error rolls the complete turn back. Model
and provider IDs, token budgets, costs, and grounding thresholds remain
environment configuration.

