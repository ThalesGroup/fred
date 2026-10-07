## Context

See [proposal.md](proposal.md) for the problem and scope. `useSessionHistory.ts` currently calls `prepare-execution` to get `messages_url_template`. `prepare_execution` refuses deleted, disabled and suspended instances, so history incorrectly inherits execution eligibility. Runtime `GET /agents/sessions/{session_id}/messages` already reads history independently of the agent and filters by authenticated owner.

`session_metadata.source_runtime_id` is captured at session creation and survives agent deletion. Conversation erasure already resolves through that snapshot, falling back to a live instance only for older rows. The current session-detail route returns `SessionListItem`, validates team access, and does not check session ownership itself. Sidebar `ChatList` keeps sessions with an `agent_instance_id` even if that instance is no longer in the agent list.

## Goals / Non-Goals

**Goals:** Reuse persisted runtime routing and the existing detail route; establish one typed conversation state consumed by history and every chat execution entry point; keep message reads at the runtime and preserve ownership checks.

**Non-Goals:** No soft deletion, agent tombstones, stored display-name snapshots, replacement-agent selection, guessed runtime discovery or migration. No termination of a turn already admitted before deletion, and no broader session-authority redesign from issue #2770. Title management and whole-conversation deletion retain their existing meaning; read-only applies to execution and its context.

## Decisions

### 1. Extend the existing session-detail response

Introduce `SessionDetails` extending `SessionListItem` with `agent_deleted: bool` and `messages_url: str | None`. Use it only on `GET /teams/{team_id}/sessions/{session_id}`; list/create/update responses keep their lightweight shape. `agent_deleted` is true only when a non-null stored instance id cannot be resolved within the recorded team. A session without an instance is not evidence of deletion.

Resolve `messages_url` from the session's captured `source_runtime_id` and configured ingress prefix. When that snapshot is null, use its surviving instance as the compatibility fallback. Return a null URL if routing cannot be resolved from existing records/configuration; the frontend shows unavailable history explicitly. Do not call the runtime catalog or expose `base_url`, `source_runtime_id`, tuning or execution context. Add owner validation before returning the detail response; retain the runtime's independent owner filter.

This separates routing from execution with one additive detail projection, rather than introducing an endpoint family or making `prepare-execution` return a fake executable binding for a deleted agent. Generate OpenAPI and frontend types with `make update-control-plane-api`.

### 2. Load history from current session details

Give `useSessionHistory` the current session's generated details and concrete history URL. Remove its execution-preparation mutation. Keep cached initial rendering, visit tracking, stale-session rejection and protection against replacing an active or optimistic turn. A newly bound session waits for its row/details before fetching history; a transient metadata 404 during creation must not erase its optimistic messages. Expose a distinct loading/unavailable result so failed reads no longer silently become an empty thread.

`useManagedChat` derives saved-conversation availability from current session details, with no deleted-agent inference from an empty catalog or a failed request. Before any confirmed result, saved sessions withhold execution; an existing valid cached result can remain usable during revalidation, with normal preparation still enforcing server-side eligibility. Fresh chats retain their existing execution preparation.

### 3. Gate every execution entry point

Consume one read-only state in `ManagedChatPage`, `useManagedChat`, `ConversationThread` and the attachment drawer. Disable or omit the composer and its command/voice/file-drop/paste actions, retry and new-conversation actions, context/library/document selectors and persisted attachment removal. Add guards to the hook callbacks for send/commands, HITL single/batch/skip and Graph continuation/restart, so an indirect caller cannot bypass disabled UI. Avoid eager composer/model preparation for a confirmed deleted instance.

Keep unanswered historical HITL prompts visible as frozen cards, including the trailing prompt currently reserved for the live interaction. Keep interrupted-execution details readable without recovery buttons. Existing source/trace reads and attachment downloads remain available. Add localized English/French notices and append the exact `(deleted)` suffix to the agent label in the chat header and sidebar. Reuse an available name and the existing generic agent label when no name survives deletion; no display-name migration is introduced. Do not redesign the layout or styles beyond the notice and state wiring.

### 4. Refresh availability using existing query tags

Make the session-detail query provide its session tag and the linked `ControlPlaneAgentInstance` tag. The existing agent-delete mutation already invalidates the instance tag, so active details refetch without a new polling loop. Use existing cross-session/focus refresh conventions when revisiting the conversation. If deletion occurs after a live snapshot was read, ordinary execution preparation/runtime binding still refuses it; preserve the draft and refresh availability on that refusal. Do not claim cross-process cancellation of already admitted turns.

### 5. Keep one lifecycle spec and existing interaction contracts

The new `managed-conversations` capability covers durable history and the conversation's ability to execute. Existing agent-question and interrupted-execution specifications govern interactions when execution is available; frozen history offers no resume after deletion. Reuse the existing product-contract session section and component-UX chat section for boundary notes and links, instead of adding another RFC or status document.

## Risks / Trade-offs

- Older rows can lack a runtime snapshot and their instance may already be gone -> show unavailable history explicitly; do not route to an arbitrary configured runtime. Recovering missing historical routing needs separate evidence and is outside this change.
- Runtime removal/outage can prevent reads even though history still exists -> distinguish an unavailable-history warning from confirmed deletion and preserve cached messages.
- The session-detail ownership guard can reject a team member's previous metadata-only access to another user's session -> this endpoint serves private chat details, matching list and runtime owner scoping. Cover the refusal in API tests; broader ownership work stays in #2770.
- Deleted-agent detection can be stale across clients -> refetch via existing invalidation/refresh paths, and rely on existing backend preparation/binding rejection for requests racing deletion.
- Large chat hooks already combine many interactions -> keep the state derivation focused and reuse it; extract a focused helper only where needed to avoid adding another independent concern to the large hook.

## Migration Plan

No schema, permission-model or configuration changes. Deploy the paired Control Plane/frontend release normally. The detail response is additive for old clients; new frontend code requires the new response for deleted-agent history. Roll back the paired application release normally; history/session data is preserved and the old UI's deletion defect returns. The migration note initially covers planning-only files and must be reconciled with the actual implementation before readiness.

The initial local-session creation handoff remains executable while its metadata
POST settles, and known failed local creations retain their existing same-id
retry. This exemption ends on a successful detail response or navigation away;
later saved-session visits require confirmed metadata. A runtime HTTP refusal
before admission rolls back the optimistic turn and restores the draft, then
refetches availability without inferring deletion from the refusal itself.
