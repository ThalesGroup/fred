# Proposal

## Why

Deep parent model requests omit Fred's existing checkpoint hygiene, allowing dangling tool calls and provider reasoning blocks to reach providers. Named assistant messages also trigger Mistral's forbidden-field validation. This is the approved extraction slice of issues #2740 and #2741.

## What Changes

- Add existing request-only checkpoint hygiene ahead of Deep parent capability middleware.
- Strip message names from copied model inputs through shared hygiene, preserving checkpoint objects and tool pairing.
- Keep Deep message-count trimming disabled; retain the existing character budget and defer compaction work.
- Validate provider serialization and parent execution. Native-child wiring and its acceptance tests belong to the next extraction layer; both issues remain open.

## Capabilities

### New Capabilities

- `model-input-hygiene`: Request-only sanitation shared by ReAct and Deep, including provider-compatible message names.

### Modified Capabilities

None. The in-flight Deep baseline describes runtime dispatch and HITL; this slice adds a shared input requirement without changing those contracts.

## Impact

Runtime Deep middleware composition, shared checkpoint hygiene and tool-loop helpers, focused runtime tests, and the compact execution contract. No public API, provider configuration, filesystem backend, or dependency changes.
