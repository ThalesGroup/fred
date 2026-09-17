## Why

Deep Agents publish their current plan through `write_todos`, but Fred renders that state as a generic tool call inside each turn's reasoning trace. Users cannot keep the active work plan in view while the conversation scrolls, even though the complete snapshots are already persisted in `session_history`.

## What Changes

- Add a collapsible, composer-aligned task panel between the scrollable conversation and the chat composer.
- Derive the panel from the latest valid `write_todos` tool-call snapshot already present in the conversation message history, without introducing another API or persistence model.
- Display pending, in-progress, and completed tasks with distinct visual and accessible states and report the number of unfinished tasks.
- Persist the user's expanded or collapsed choice per conversation while restoring task content from the existing conversation history.
- Remove valid `write_todos` call/result pairs from `ThoughtTrace` when the dedicated panel represents them, while retaining malformed calls in the trace for diagnosis.
- Add English and French copy and document the new chat UX component.

## Capabilities

### New Capabilities

- `deep-agent-todo-panel`: Projects persisted Deep Agent `write_todos` snapshots into a dedicated, collapsible chat task panel and prevents duplicate generic trace rows.

### Modified Capabilities

None.

## Impact

- Frontend chat presentation in `apps/frontend/src/rework/`, including the managed chat page, trace grouping, a new shared molecule, localization, and focused tests.
- Chat UX documentation in `docs/swift/ux/COMPONENT-UX.md`.
- No runtime, control-plane, OpenAPI, database, or generated-client change.
- Tracked by GitHub issue #2724. This is separate from #2328: `write_todos` remains conversation planning state and is not synchronized with workspace `TODO.md`.
