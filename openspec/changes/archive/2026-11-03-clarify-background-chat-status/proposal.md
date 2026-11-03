## Why

The sidebar currently represents a pending user question with a dot and halo, while completed background answers only bold the title. The user requested a readable waiting chip and a simple blue completed-answer dot in PR #3429, extending issue #3427.

## What Changes

- Display a compact, contrasted "Awaiting reply" / "Réponse attendue" chip below the sidebar title and metadata when the conversation needs user input.
- Keep animated dots for running generations. Show a plain blue dot, without shadow, for a successfully completed background answer until the conversation is opened.
- Do not signal errors, cancelled turns or premature stream endings as answers ready to read.
- Restore the open conversation's pending-input chip from its already loaded history after reload; other sessions remain unknown until opened.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `managed-conversations`: distinguish background running, user-input and completed-unread states.

## Impact

Existing browser registry, SSE terminal events, sidebar rendering, translations and focused tests. Reuse the existing operator note and UX documentation in this PR. No backend/API, deployment configuration or migration change.
