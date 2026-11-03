## Why

PR #3418 lets a streamed answer survive navigation, but its waiting messages are still discarded. The user approved retaining them in this browser tab and resuming their ordinary sends only after returning to the conversation (issue #3427).

## What Changes

- Keep pending messages per session in the existing background-turn registry.
- Preserve delivery updates while detached; resume FIFO only in the visible conversation, after generation and human-input holds end.
- Clear the matching queue on Stop, deletion or real stream interruption. Reload and tab close still lose browser memory.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `managed-conversations`: retain the queue across in-app navigation without background execution of queued turns.

## Impact

Frontend registry, managed-chat state, SSE lifecycle, focused tests and existing UX/operator guidance. No runtime, API, database, migration or deployment change.
