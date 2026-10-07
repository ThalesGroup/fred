## Context

See [proposal.md](proposal.md) for the problem and scope. `useSessionHistory.ts` currently calls `prepare-execution` to get `messages_url_template`. `prepare_execution` refuses deleted, disabled and suspended instances, so history incorrectly inherits execution eligibility. Runtime `GET /agents/sessions/{session_id}/messages` already reads history independently of the agent and filters by authenticated owner.

`session_metadata.source_runtime_id` is captured at session creation and survives agent deletion. Conversation erasure already resolves through that snapshot, falling back to a live instance only for older rows. The current session-detail route returns `SessionListItem`, validates team access, and does not check session ownership itself. Sidebar `ChatList` keeps sessions with an `agent_instance_id` even if that instance is no longer in the agent list.

## Goals / Non-Goals

**Goals:** Reuse persisted runtime routing and the existing detail route; establish one typed conversation state consumed by history and every chat execution entry point; keep message reads at the runtime and preserve ownership checks.

**Non-Goals:** No soft deletion, agent tombstones, replacement-agent selection or guessed runtime discovery. No termination of a turn already admitted before deletion, and no broader session-authority redesign from issue #2770. Title management and whole-conversation deletion retain their existing meaning; read-only applies to execution and its context.

## Decisions

### 1. Extend the existing session-detail response

Introduce `SessionDetails` extending `SessionListItem` with `agent_deleted: bool` and `messages_url: str | None`. Use it only on `GET /teams/{team_id}/sessions/{session_id}`; list/create/update responses keep their lightweight shape with an additive nullable `agent_display_name` snapshot. Details prefer the live instance name when it exists. `agent_deleted` is true only when a non-null stored instance id cannot be resolved within the recorded team. A session without an instance is not evidence of deletion.

Resolve `messages_url` from the session's captured `source_runtime_id` and configured ingress prefix. When that snapshot is null, use its surviving instance as the compatibility fallback. Return a null URL if routing cannot be resolved from existing records/configuration; the frontend shows unavailable history explicitly. Do not call the runtime catalog or expose `base_url`, `source_runtime_id`, tuning or execution context. Add owner validation before returning the detail response; retain the runtime's independent owner filter.

This separates routing from execution with one additive detail projection, rather than introducing an endpoint family or making `prepare-execution` return a fake executable binding for a deleted agent. Generate OpenAPI and frontend types with `make update-control-plane-api`.

### 2. Load history from current session details

Give `useSessionHistory` the current session's generated details and concrete history URL. Remove its execution-preparation mutation. Keep cached initial rendering, visit tracking, stale-session rejection and protection against replacing an active or optimistic turn. A newly bound session waits for its row/details before fetching history; a transient metadata 404 during creation must not erase its optimistic messages. Expose a distinct loading/unavailable result so failed reads no longer silently become an empty thread.

`useManagedChat` derives saved-conversation availability from current session details, with no deleted-agent inference from an empty catalog or a failed request. Before any confirmed result, saved sessions withhold execution; an existing valid cached result can remain usable during revalidation, with normal preparation still enforcing server-side eligibility. Fresh chats retain their existing execution preparation.

### 3. Gate every execution entry point

Consume one read-only state in `ManagedChatPage`, `useManagedChat`, `ConversationThread` and the attachment drawer. Disable the visible composer and disable or omit its command/voice/file-drop/paste actions, retry and new-conversation actions, context/library/document selectors and persisted attachment removal. Add guards to the hook callbacks for send/commands, HITL single/batch/skip and Graph continuation/restart, so an indirect caller cannot bypass disabled UI. Avoid eager composer/model preparation for a confirmed deleted instance.

Keep unanswered historical HITL prompts visible as frozen cards, including the trailing prompt currently reserved for the live interaction. Keep interrupted-execution details readable without recovery buttons. Existing source/trace reads and attachment downloads remain available. Add localized English/French notices and strike through only the agent name in the chat header and sidebar, including grouped headers. Keep the conversation title and navigation readable. Provide an accessible deleted/read-only description and tooltip on hover and keyboard focus. Keep the composer visible and natively disabled with a localized read-only placeholder and disabled surface/text tokens. Preserve any draft without allowing submission.

### 4. Refresh availability using existing query tags

Make the session-detail query provide its session tag and the linked `ControlPlaneAgentInstance` tag. The existing agent-delete mutation already invalidates the instance tag, so active details refetch without a new polling loop. Use existing cross-session/focus refresh conventions when revisiting the conversation. If deletion occurs after a live snapshot was read, ordinary execution preparation/runtime binding still refuses it; preserve the draft and refresh availability on that refusal. Do not claim cross-process cancellation of already admitted turns.

### 5. Keep one lifecycle spec and existing interaction contracts

The new `managed-conversations` capability covers durable history and the conversation's ability to execute. Existing agent-question and interrupted-execution specifications govern interactions when execution is available; frozen history offers no resume after deletion. Reuse the existing product-contract session section and component-UX chat section for boundary notes and links, instead of adding another RFC or status document.

### 6. Capture the name in existing session metadata

Add nullable `agent_display_name` to `session_metadata` and its list/detail projections. Capture the live runtime and name from a locked instance row in the same transaction as session insertion. Refuse creation with 404 when deletion wins or the instance belongs to another team. Before deleting an instance, lock it and snapshot its latest name into its team's sessions in the same database transaction as deletion. This preserves renamed agents without retaining a separate tombstone. Snapshot updates must not advance conversation activity timestamps. The sidebar prefers the live catalog name, then the snapshot; details prefer a live name, then the snapshot. Inactive-conversation previews use the same fallback. Group sidebar entries by instance identity so two agents sharing a name remain distinct.

Use one migration to add the column and backfill names for agents still present. Names for instances deleted before the migration cannot be reconstructed and keep the localized generic fallback. Storing the name on the conversation fits its existing lifecycle and erasure, unlike a new agent archive or frontend-only cache.

## Risks / Trade-offs

- Older rows can lack a runtime snapshot and their instance may already be gone -> show unavailable history explicitly; do not route to an arbitrary configured runtime. Recovering missing historical routing needs separate evidence and is outside this change.
- Runtime removal/outage can prevent reads even though history still exists -> distinguish an unavailable-history warning from confirmed deletion and preserve cached messages.
- The session-detail ownership guard can reject a team member's previous metadata-only access to another user's session -> this endpoint serves private chat details, matching list and runtime owner scoping. Cover the refusal in API tests; broader ownership work stays in #2770.
- Deleted-agent detection can be stale across clients -> refetch via existing invalidation/refresh paths, and rely on existing backend preparation/binding rejection for requests racing deletion.
- Large chat hooks already combine many interactions -> keep the state derivation focused and reuse it; extract a focused helper only where needed to avoid adding another independent concern to the large hook.

## Migration Plan

Apply the single Control Plane Alembic migration before deploying the paired backend/frontend release. The nullable name field is additive for older clients. It backfills only still-present agents; already deleted names remain unavailable. Application rollback can retain the column and snapshots. A schema downgrade drops only the name snapshot after rolling back the application; history and session identities remain intact. No configuration or permission-model change is required.

The initial local-session creation handoff remains executable while its metadata
POST settles. Its temporary exemption ends on navigation away; known failed local
creations retain their existing same-id retry until creation or a detail read
confirms the saved row. A confirmed detail read also recovers a lost POST response,
without allowing subsequent saved-session visits to bypass availability checks.
Failed context writes remain blocking until a context write succeeds for that
session, even if a later creation retry fails or the saved row is confirmed.
A runtime HTTP refusal
before admission rolls back the optimistic turn and restores the draft, then
refetches availability without inferring deletion from the refusal itself.
