## Context

See `proposal.md` for motivation. Deep Agents install LangChain's `TodoListMiddleware`, whose `write_todos` input is a complete `todos` array of `{content, status}` items. Fred already maps each tool call into a `ChatMessage` with the arguments intact, persists those messages in runtime-owned `session_history`, and restores them through the existing history path.

`ManagedChatPage` owns the complete ordered `ChatMessage[]` and composes a scrollable conversation stage followed by an in-flow composer footer. `ThoughtTrace` currently groups every tool call and matching result into a generic trace row. The generated frontend message type already permits arbitrary tool arguments, so the change does not require a backend or generated-client edit.

## Goals / Non-Goals

**Goals:**

- Make one conversation-level todo snapshot visible throughout the current conversation.
- Preserve identical behavior for live events and restored history.
- Keep todo content single-sourced from existing conversation messages.
- Keep malformed data diagnosable and unrelated trace behavior unchanged.

**Non-Goals:**

- Letting users edit agent tasks.
- Synchronizing planning state with a workspace `TODO.md` file.
- Combining plans from independently scoped subagents.
- Adding a runtime event, API, database model, or generated type.

## Decisions

### D1 - Project existing messages instead of persisting another todo model

A pure frontend selector scans conversation messages from newest to oldest and returns the first valid `write_todos` snapshot that has not received an explicitly failed tool result. Scanning backward matches the full-snapshot semantics and avoids replaying mutations. A valid empty array is a deliberate clear operation; the selector therefore distinguishes "no valid snapshot" from "valid empty snapshot".

The alternative was a dedicated todo endpoint or frontend cache. That would duplicate runtime-owned history, create synchronization and deletion problems, and add no information that the persisted tool call does not already contain.

### D2 - Validate narrowly at the presentation boundary

The selector accepts only the exact `write_todos` name and a `todos` array whose items have non-empty string content and a recognized status. An invalid later call or one with an explicitly failed result is skipped so it cannot erase the last usable plan. The same predicate identifies which calls may safely leave the generic trace.

The alternative was permissive coercion. Coercion could hide a runtime or dependency schema change while presenting incorrect state. Leaving invalid calls in `ThoughtTrace` makes that failure visible.

### D3 - Render one conversation-level molecule above the composer

A shared `AgentTodoPanel` molecule receives the selected snapshot and the active session identifier. `ManagedChatPage` renders it between `conversationStage` and `inputOverlay`, in the non-initial state, with the same maximum-width alignment as the composer. The panel extends behind the higher-stacking composer by the corner radius plus one spacing step, while hover feedback remains confined to the `Tasks` header and never tints the backing surface through the composer. This keeps the panel visible while only the message area scrolls.

Rendering inside `AssistantTurn` was rejected because it would attach the current plan to an old exchange and scroll it out of view. Rendering inside `RichInputField` was rejected because the plan is conversation state, not composer input or an editable control.

The persisted snapshot remains the task-content source, but presentation also reads the existing final message boundary. When the same exchange contains an assistant `final` without an error entry or failed tool result, any residual `in_progress` item is presented as completed; otherwise a stale middleware snapshot would keep showing active work after the assistant has visibly finished the step. The check deliberately does not depend on array position: the streaming reducer can reserve the final frame's slot before later tool events and replace it in place at turn completion. Failed turns retain their authoritative unfinished state. If successful settlement leaves no pending work, the panel disappears instead of retaining a completed-state summary.

### D4 - Persist only the user's disclosure preference

Todo content remains in conversation history. The panel stores only a nullable expanded/collapsed preference in `localStorage`, keyed by `session_id`, using the existing storage hook. When no explicit preference exists, it opens while work remains. An explicit choice wins until the user changes it, but no preference keeps the panel visible after all work is complete.

A persistent, visually hidden polite status region remains mounted next to the panel slot. It announces the remaining count plus each task's accessible status and content, and announces completion even when the visible panel is removed.

`sessionStorage` was considered, but the requested persistence includes page reload and later returns to a conversation. The stored value is one non-sensitive boolean per conversation; no task text is copied into browser storage by this feature.

### D5 - Remove only authoritative represented calls from `ThoughtTrace`

Trace grouping filters a valid `write_todos` call and the tool result with its call identifier before producing rows unless the latest explicit result reports failure. Malformed calls, failed calls, orphan results, and every other tool retain the existing grouping behavior. This prevents double presentation without hiding error diagnostics.

The task selector operates on the page's complete message list, while trace filtering operates on each turn's trace subset. Both reuse one strict parser so "represented" cannot mean different things in the two paths.

### D6 - Keep subagent scope out until the runtime identifies it

The panel reflects only `write_todos` calls that Fred exposes in the top-level ordered conversation message stream. The current tool-call event and stored message do not carry a subgraph or agent-scope identifier, so merging separately scoped plans would be ambiguous. If scoped subagent todo events become product-visible later, they require an explicit identity contract before the UI combines or switches between them.

## Risks / Trade-offs

- **A future dependency changes the `write_todos` payload shape** -> strict validation leaves the call visible in `ThoughtTrace` instead of silently presenting corrupted state; focused parser tests pin the supported shape.
- **A long conversation is rescanned during streaming** -> scan newest-first inside a memoized selector and stop at the first valid snapshot; no parsing or rendering work is added to the backend hot path.
- **A valid call arrives before its result or the result fails** -> the panel can update optimistically while the call is pending, but an explicitly failed result restores the preceding successful snapshot and keeps the failed call/result visible in the trace.
- **The panel consumes too much vertical space** -> keep the header compact, constrain the expanded body, and make disclosure persistent per conversation.
- **`write_todos` and workspace `TODO.md` are mistaken for synchronized records** -> document them as separate concepts and never read or write `TODO.md` from this feature.

## Migration Plan

No data migration or rollout coordination is required. Deploy the frontend with its parser, component, trace filtering, localization, and documentation together. Rollback removes only the specialized projection; persisted conversation messages continue to render through the existing generic trace.
