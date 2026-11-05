## Context

See proposal.md for the user-visible defect. `get_session_messages` currently returns stored rows unchanged; `reconstructPendingHitls` equates an absent history response with a live pause. Checkpoint progress and single-use claims are independent shared state. A local read-only investigation confirmed a consumed `ask_user` result with no corresponding history response. Runtime contract section 8.89 intentionally excludes history persistence on disconnection; this change keeps that lifecycle unchanged.

## Goals / Non-Goals

**Goals:** make an unavailable historical HITL question noninteractive on reload, preserve legitimate pending questions, and avoid an invented success or failure.

**Non-Goals:** resume or keep an execution alive across refresh, release claims, repair stored history, change cancellation, or infer the user's answer from incomplete history.

## Decisions

1. Add an optional typed `resume_status` to HITL request parts in history responses (`pending`, `unavailable`, `unknown`). Compute it on authorized reads for unanswered requests in the trailing exchange, without persisting the annotation. The SQL history reader exposes its persisted agent instance as the existing `metadata.agent_id` on HITL rows to locate managed Graph threads. Regenerate the affected API schemas/clients. Old clients ignore the addition; new clients retain existing behavior for an omitted field from an older server. Explicit `unknown` disables answer controls and offers a lookup retry while preserving readable history.
2. Reuse the resume gate's identity and thread-location semantics. Inspect the latest relevant checkpoint's interrupt writes and matching durable claims. A pending identity with no blocking claim is `pending`; an absent identity or a started/consumed claim is `unavailable`. A live pre-start claim is unavailable for duplicate submission while held; reclaimable claims follow the existing database-clock expiry rule. Missing storage, decoding failures or unsupported legacy identity are `unknown`, never proof of failure. No graph activation, model/tool execution, claim mutation or transcript reconstruction is performed.
3. Perform the ownership-filtered history read first. For authorized nonempty history only, use bounded checkpoint/claim queries for the relevant thread candidates and unanswered occurrence set, with configured connection pools. Do not call the admin checkpoint inventory endpoint or load every historical checkpoint/channel blob. Shared storage makes the result consistent across replicas; admission remains authoritative if a concurrent answer races the read.
4. Pass availability through history reconstruction and trace presentation. `unavailable` shows a neutral, noninteractive notice: FR "Cette question ne peut plus recevoir de réponse." / EN "This question can no longer accept an answer." It must not keep the question labelled waiting/running, synthesize a failed tool result, or assert that the continuation completed. Known real tool results retain precedence. A known obsolete 409 refreshes this same authorized history view, guarded against session switches; retryable conflicts preserve the existing draft behavior.
5. Keep the initial fix independent of active-turn reconnection and disconnected-history persistence. Read-time reconciliation also handles existing inconsistent rows without editing the user's session.

## Risks / Trade-offs

- A read can race a resume -> retain the server admission checks and refresh availability after a known stale rejection; do not auto-submit.
- A runtime may be unavailable -> show an unknown state with retry, not an obsolete/failed question.
- Reads add database work -> inspect only the trailing unanswered set, reuse pools, and test fixed query growth rather than one query per historical message.
- Mixed frontend/backend versions -> additive optional schema; definitive behavior requires the updated runtime, documented in the migration note.
- A started claim may belong to an active continuation -> use neutral unavailable wording, not "failed" or "interrupted", unless separate authoritative evidence proves it.

## Migration Plan

No schema or data migration. Deploy runtime and frontend normally; older runtimes retain legacy rendering during rollout. Roll back the code without editing history or checkpoints. Keep runtime contract section 8.89 intact and document only the read-time availability contract. Existing public tracking remains #2337 and lifecycle context #1080.
